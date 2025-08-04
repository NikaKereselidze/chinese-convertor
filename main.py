from flask import Flask, render_template, request, jsonify
import pypinyin
import re
import itertools
from pypinyin_dict.pinyin_data import kxhc1983
from flask_cors import CORS
import unicodedata
# Load the pinyin data
kxhc1983.load()

app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "*"}})

# Add security headers
@app.after_request
def add_security_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Content-Security-Policy'] = "frame-ancestors *"
    response.headers['X-Frame-Options'] = 'ALLOWALL'
    return response

def get_pinyin(words):
    if not words:
        return []
    pinyin_list = []
    for word in words:
        for char in word:
            pinyin_result = pypinyin.pinyin(char, style=0, heteronym=True)
            pinyin_list.append(pinyin_result)

    all_result = []
    pinyin_list = [item[0] for item in pinyin_list]
    pinyin_cartesian = list(itertools.product(*pinyin_list))
    all_result = [' '.join(pinyin).replace('v', 'ü') for pinyin in pinyin_cartesian]
    return all_result

def get_professional_pinyin(text):
    import pypinyin
    from pypinyin import Style
    pinyin_list = pypinyin.pinyin(text, style=Style.TONE, heteronym=False, errors='default', strict=True)
    return ' '.join([item[0] for item in pinyin_list])

def remove_pinyin_tone_marks(pinyin):
    # Replace diacritics with their base letter
    return ''.join(
        c for c in unicodedata.normalize('NFD', pinyin)
        if unicodedata.category(c) != 'Mn'
    )

def get_georgian(pinyin_list):
    if not pinyin_list:
        return {}
    all_result = {}
    for pinyin in pinyin_list:
        replacements_long = {
            'ci': 'ც',
            'si': 'ს',
            'zh': 'ჭ',
            'ch': 'ჩ',
            'sh': 'შ',
            'er': 'ერ',
            'yi': 'i',
            'wu': 'u',
            'yu': 'iu',
            'ya': 'ia',
            'iu': 'iou',
            'ng': 'ნგ',
            'ong': 'უნგ',
            'ui': 'uei'
        }
        pattern = '|'.join(re.escape(char) for char in replacements_long.keys())
        text_long = re.sub(pattern, lambda match: replacements_long[match.group()], pinyin)

        text_long = re.sub(r'(?<=[jqxy])u', 'iu', text_long)
        if 'iuan' in text_long and 'g' not in text_long[text_long.index('iuan')+3:]:
            text_long = text_long.replace('iuan', 'iuen')
        if 'ian' in text_long:
            text_long = text_long.replace('ian', 'ien')

        replacements_short = {
            'b': 'პ',
            'p': 'ფ',
            'm': 'მ',
            'f': 'ფ',
            'd': 'ტ',
            't': 'თ',
            'n': 'ნ',
            'l': 'ლ',
            'g': 'კ',
            'k': 'ქ',
            'h': 'ხ',
            'j': 'ძ',
            'q': 'ც',
            'x': 'ს',
            'z': 'წ',
            'c': 'ც',
            's': 'ს',
            'r': 'ჟ',
            'y': 'ი',
            'w': 'ვ',
            'a': 'ა',
            'o': 'ო',
            'e': 'ე',
            'i': 'ი',
            'u': 'უ',
            'ü': 'იუ'
        }
        pattern_short = '|'.join(re.escape(char) for char in replacements_short.keys())
        text_short = re.sub(pattern_short, lambda match: replacements_short[match.group()], text_long)
        text_short = text_short.replace(' ', '')
        pinyin = pinyin.replace(' ', '')

        all_result[pinyin] = text_short

    return all_result

def map_pinyin_to_georgian(pinyin_str):
    # Split by spaces, remove tone marks, map each to Georgian, join with space
    syllables = pinyin_str.strip().split()
    plain_syllables = [remove_pinyin_tone_marks(s) for s in syllables]
    georgian_syllables = [get_georgian([s]).get(s, '') for s in plain_syllables]
    return ' '.join(georgian_syllables).strip()

def convert(data):
    try:
        mode = data.get('mode', 'chinese')
        special_cases = {
            "北京": "პეკინი",
            "南京": "ნანკინი",
            "陕西": "შაანსი",
            "香港": "ჰონგკონგი",
            "澳门": "მაკაო",
            "西藏": "ტიბეტი",
            "乌鲁木齐": "ურუმჩი",
            "中山孙": "სუნ იატსენი",
            "介石蒋": "ჩან კაიში",
            "小龙李": "ბრუს ლი",
            "成龙": "ჯეკი ჩანი",
            "成吉思汗": "ჩინგიზ-ყაენი",
            "忽必烈": "ყუბილაი",
            "孔子": "კონფუცი",
        }
        if mode == 'pinyin':
            first_name = data.get('first_name_pinyin', '').strip().lower()
            last_name = data.get('last_name_pinyin', '').strip().lower()
            others = data.get('others_pinyin', '').strip().lower()
            # If all are empty, error
            if not (first_name or last_name or others):
                return {'error': 'Please enter at least one pinyin field.'}
            # Special case check for combinations
            def match_special(pinyin):
                for hanzi, geo in special_cases.items():
                    special_pinyin = get_professional_pinyin(hanzi)
                    if pinyin.replace(' ', '').lower() == special_pinyin.replace(' ', '').lower():
                        return geo
                return None
            from collections import OrderedDict
            result = OrderedDict()
            if first_name and last_name:
                # Check special case for full name combinations
                full_name_1 = f"{first_name} {last_name}".strip()
                full_name_2 = f"{last_name} {first_name}".strip()
                geo1 = match_special(full_name_1)
                geo2 = match_special(full_name_2)
                georgian1 = geo1 or map_pinyin_to_georgian(full_name_1)
                georgian2 = geo2 or map_pinyin_to_georgian(full_name_2)
                result['სახელი+გვარი'] = {
                    'pinyin': full_name_1,
                    'ქართული': georgian1
                }
                result['გვარი+სახელი'] = {
                    'pinyin': full_name_2,
                    'ქართული': georgian2
                }
            elif first_name and not last_name:
                geo = match_special(first_name)
                georgian = geo or map_pinyin_to_georgian(first_name)
                result['სახელი'] = {
                    'pinyin': first_name,
                    'ქართული': georgian
                }
            elif not first_name and last_name:
                geo = match_special(last_name)
                georgian = geo or map_pinyin_to_georgian(last_name)
                result['გვარი'] = {
                    'pinyin': last_name,
                    'ქართული': georgian
                }
            elif others:
                geo = match_special(others)
                georgian = geo or map_pinyin_to_georgian(others)
                result['სახელი'] = {
                    'pinyin': others,
                    'ქართული': georgian
                }
            return result

        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')
        others = data.get('others', '')

        if others:
            special_case_key = others
        else:
            special_case_key = (first_name, last_name)

        if special_case_key in special_cases:
            # Determine which field was used for the special case
            if others:
                input_text = others
            elif first_name and last_name:
                input_text = f"{first_name}{last_name}"
            else:
                input_text = first_name or last_name or ''
            prof_pinyin = get_professional_pinyin(input_text) if input_text else None
            return {"special": {"pinyin": prof_pinyin, "ქართული": special_cases[special_case_key]}}
        
        if not bool(first_name) and not bool(last_name) and not bool(others):
            return {"error": "All input fields are empty.\nყველა შეყვანის ნაწილი ცარიელია."}

        if not (re.search(r'[\u4e00-\u9fa5]', first_name) or
                re.search(r'[\u4e00-\u9fa5]', last_name) or
                re.search(r'[\u4e00-\u9fa5]', others)):
            return {"error": "Please enter Chinese characters.\nგთხოვთ შეიყვანოთ ჩინური იეროგლიფი."}

        first_name_pinyin = get_pinyin(first_name)
        last_name_pinyin = get_pinyin(last_name)
        others_pinyin = get_pinyin(others)

        first_name_georgian = get_georgian(first_name_pinyin)
        last_name_georgian = get_georgian(last_name_pinyin)
        others_georgian = get_georgian(others_pinyin)

        first_name_key = list(first_name_georgian.keys())
        last_name_key = list(last_name_georgian.keys())
        cartesian_product = list(itertools.product(first_name_key, last_name_key))

        merged_dict_1 = {}
        merged_dict_2 = {}
        for first_name_key, last_name_key in cartesian_product:
            key_conbination_1 = f"{first_name_key} {last_name_key}"
            value_conbination_1 = f"{first_name_georgian[first_name_key]} {last_name_georgian[last_name_key]}"
            merged_dict_1[key_conbination_1] = value_conbination_1

            key_conbination_2 = f"{last_name_key} {first_name_key}"
            value_conbination_2 = f"{last_name_georgian[last_name_key]} {first_name_georgian[first_name_key]}"
            merged_dict_2[key_conbination_2] = value_conbination_2

        # Professional pinyin with tone marks and word segmentation
        from collections import OrderedDict
        result = OrderedDict()
        if bool(first_name) and bool(last_name):
            full_name_1 = f"{first_name}{last_name}"
            full_name_2 = f"{last_name}{first_name}"
            full_name_1_prof_pinyin = get_professional_pinyin(full_name_1) if full_name_1 else ''
            full_name_2_prof_pinyin = get_professional_pinyin(full_name_2) if full_name_2 else ''
            result['სახელი+გვარი'] = {
                'pinyin': full_name_1_prof_pinyin,
                'ქართული': ' '.join(merged_dict_1.values())
            }
            result['გვარი+სახელი'] = {
                'pinyin': full_name_2_prof_pinyin,
                'ქართული': ' '.join(merged_dict_2.values())
            }
        elif bool(first_name) and not bool(last_name):
            first_name_prof_pinyin = get_professional_pinyin(first_name) if first_name else ''
            result['სახელი'] = {
                'pinyin': first_name_prof_pinyin,
                'ქართული': ' '.join(first_name_georgian.values())
            }
        elif not bool(first_name) and bool(last_name):
            last_name_prof_pinyin = get_professional_pinyin(last_name) if last_name else ''
            result['გვარი'] = {
                'pinyin': last_name_prof_pinyin,
                'ქართული': ' '.join(last_name_georgian.values())
            }
        elif others_georgian:
            others_prof_pinyin = get_professional_pinyin(others) if others else ''
            result['სახელი'] = {
                'pinyin': others_prof_pinyin,
                'ქართული': ' '.join(others_georgian.values())
            }
        else:
            result = {"error": "No valid input provided"}
        
        return result
        
    except Exception as e:
        return {"error": str(e)}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST', 'OPTIONS'])
def convert_endpoint():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 400
        data = request.get_json()
        if data is None:
            return jsonify({"error": "Invalid JSON data"}), 400
        print("Received data:", data)
        result = convert(data)
        print("test", result)
        if isinstance(result, str):
            return jsonify({"result": result})
        elif result is None:
            return jsonify({"error": "No result generated"}), 400
        else:
            return jsonify(result)
    except Exception as e:
        app.logger.error(f"Error in convert_endpoint: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    try:
        with open("datasur.txt", "r", encoding="utf-8") as infile, \
             open("datasur_converted.txt", "w", encoding="utf-8") as outfile:
            lines = [line.strip() for line in infile if line.strip()]
            outfile.write("Original\t=>\tGeorgian\n")
            for line in lines:
                result = convert({'text': line})
                georgian = result.get('result', '')
                if isinstance(georgian, dict):
                    georgian = ', '.join(georgian.values())
                outfile.write(f"{line}\t=>\t{georgian}\n")
    except Exception as e:
        print(f"Error processing datasur.txt: {e}")

    app.run(debug=True, port=8080, host='0.0.0.0') 
