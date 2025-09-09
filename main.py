from flask import Flask, render_template, request, jsonify
import pypinyin
import re
import itertools
from pypinyin_dict.pinyin_data import kxhc1983
from flask_cors import CORS
import unicodedata
import os
import csv
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
    
    # Use primary pronunciations only (most common)
    # pinyin_list = []
    # for word in words:
    #     word_pinyin = pypinyin.pinyin(word, style=0, heteronym=False)
    #     word_result = ' '.join([item[0] for item in word_pinyin])
    #     pinyin_list.append(word_result)
    pinyin_result = pypinyin.pinyin(words, style=0, heteronym=True)
    result_tuples = list(itertools.product(*pinyin_result))
    all_result = [' '.join(items) for items in result_tuples]
    return all_result

def get_professional_pinyin(text):
    import pypinyin
    from pypinyin import Style
    pinyin_list = pypinyin.pinyin(text, style=0, heteronym=False, errors='default', strict=True)
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

def deduplicate_preserve_order(items):
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result

def group_tone_variants_by_base(pinyin_list_with_tones):
    """Group tone-marked pinyin variants by their base (without tone marks)."""
    base_to_variants = {}
    order = []
    for p in pinyin_list_with_tones:
        base = remove_pinyin_tone_marks(p)
        if base not in base_to_variants:
            base_to_variants[base] = []
            order.append(base)
        if p not in base_to_variants[base]:
            base_to_variants[base].append(p)
    return order, base_to_variants

def deduplicate_preserve_order(items):
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result

# ---------------- Polyphonic data loading (Excel/CSV) ----------------
def contains_cjk(text: str) -> bool:
    """Return True if any char is in common CJK ranges (incl. extensions)."""
    for ch in text:
        cp = ord(ch)
        if (
            0x3400 <= cp <= 0x4DBF or  # CJK Ext A
            0x4E00 <= cp <= 0x9FFF or  # CJK Unified
            0xF900 <= cp <= 0xFAFF or  # CJK Compatibility Ideographs
            0x20000 <= cp <= 0x2A6DF or  # CJK Ext B
            0x2A700 <= cp <= 0x2B73F or  # CJK Ext C
            0x2B740 <= cp <= 0x2B81F or  # CJK Ext D
            0x2B820 <= cp <= 0x2CEAF or  # CJK Ext E
            0x2F800 <= cp <= 0x2FA1F     # CJK Compatibility Ideographs Suppl.
        ):
            return True
    return False
def load_polyphonic_data():
    """Load mapping from Chinese simplified char to list of readings from CSV/XLSX.

    Priority:
    1) polyphonic_full.csv in workspace root
    2) polyphonic_full.xlsx in workspace root
    3) polyphonic_full.csv in user's Downloads
    Returns dict: char_simpl -> { 'all_readings': str, 'readings_list': [str, ...] }
    """
    candidates = [
        os.path.join(os.getcwd(), 'polyphonic_full.csv'),
        os.path.join(os.path.expanduser('~'), 'Downloads', 'polyphonic_full.csv'),
    ]

    mapping = {}
    source_path = next((p for p in candidates if os.path.isfile(p)), None)
    if not source_path:
        return mapping

    try:
        with open(source_path, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            # Expect columns: char_simpl, all_readings
            for row in reader:
                char = str(row.get('char_simpl', '')).strip()
                readings = str(row.get('all_readings', '')).strip()
                if not char or not readings:
                    continue
                tokens = [t.strip() for t in readings.split(' ') if t.strip()]
                if not tokens:
                    continue
                mapping[char] = {
                    'all_readings': readings,
                    'readings_list': tokens,
                }
    except Exception:
        # If CSV read fails, leave mapping empty to fallback gracefully
        return {}

    return mapping


POLYPHONIC_MAP = load_polyphonic_data()

def lookup_polyphonic_readings(text):
    """If text is a single Chinese char and exists in the polyphonic map,
    return (main_pinyin, other_pinyins_list). Otherwise return None.
    """
    if not text or len(text) != 1:
        return None
    data = POLYPHONIC_MAP.get(text)
    if not data:
        return None
    readings = data.get('readings_list', [])
    if not readings:
        return None
    main = readings[0]
    others = readings[1:] if len(readings) > 1 else []
    return (main, others)

def convert(data):
    try:
        # Get the single input text and tone toggle
        text = data.get('text', '').strip()
        include_tones = bool(data.get('include_tones', False))
        
        if not text:
            return {'error': 'Please enter some text.\nგთხოვთ შეიყვანოთ ტექსტი.'}
        
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
        
        # Check if input contains Chinese characters (include CJK extensions)
        has_chinese = contains_cjk(text)
        
        if has_chinese:
            # Handle Chinese input
            # Check for special cases first
            if text in special_cases:
                prof_pinyin = get_professional_pinyin(text)
                return {"special": {"pinyin": prof_pinyin, "ქართული": special_cases[text]}}
            
            # Try polyphonic data lookup for single character
            polyphonic = lookup_polyphonic_readings(text)
            if polyphonic is not None:
                main_pinyin, other_pinyins = polyphonic
                # Group tone variants by base from tone-marked forms
                all_with_tones = [main_pinyin] + other_pinyins
                bases_order, base_to_variants = group_tone_variants_by_base(all_with_tones)

                # Normalize pinyin (strip tones) and deduplicate
                main_plain = remove_pinyin_tone_marks(main_pinyin)
                others_plain = [remove_pinyin_tone_marks(p) for p in other_pinyins]
                others_plain = [p for p in others_plain if p and p != main_plain]
                others_plain = deduplicate_preserve_order(others_plain)

                # Convert to Georgian from normalized pinyin and deduplicate
                georgian_result = map_pinyin_to_georgian(main_plain)
                other_georgians = [map_pinyin_to_georgian(p) for p in others_plain]
                other_georgians = [g for g in other_georgians if g and g != georgian_result]
                other_georgians = deduplicate_preserve_order(other_georgians)

                from collections import OrderedDict
                result = OrderedDict()
                result['ქართული'] = {
                    'pinyin': main_plain,
                    'other_pinyin': others_plain,
                    'other_georgian': other_georgians,
                    'ქართული': georgian_result
                }
                if include_tones:
                    grouped_pinyin = [', '.join(base_to_variants[b]) for b in bases_order]
                    grouped_georgian = [map_pinyin_to_georgian(b) for b in bases_order]
                    result['ქართული']['grouped_pinyin'] = grouped_pinyin
                    result['ქართული']['grouped_georgian'] = grouped_georgian
                return result

            # Regular Chinese processing (fallback)
            text_pinyin = get_pinyin([text])
            text_prof_pinyin = get_professional_pinyin(text)
            
            # Compute variants (tone-less) using heteronyms
            # text_pinyin is combinations (no tones) with first as main
            base_variants = []
            if isinstance(text_pinyin, list) and len(text_pinyin) > 0:
                base_variants = text_pinyin
            # Deduplicate while preserving order
            base_variants_dedup = []
            seen_b = set()
            for v in base_variants:
                v_plain = remove_pinyin_tone_marks(v).strip()
                if v_plain and v_plain not in seen_b:
                    seen_b.add(v_plain)
                    base_variants_dedup.append(v_plain)
            main_base = base_variants_dedup[0] if base_variants_dedup else remove_pinyin_tone_marks(text_prof_pinyin)
            other_bases = base_variants_dedup[1:] if len(base_variants_dedup) > 1 else []
            
            # Convert to Georgian with proper spacing
            georgian_result = map_pinyin_to_georgian(main_base)
            other_georgians = [map_pinyin_to_georgian(p) for p in other_bases]
            other_georgians = [g for g in other_georgians if g and g != georgian_result]
            
            # Grouped tone variants when requested
            grouped_pinyin = None
            grouped_georgian = None
            if include_tones:
                try:
                    from pypinyin import Style
                    # Get tone variants per syllable with heteronyms
                    tone_syllables = pypinyin.pinyin(text, style=Style.TONE, heteronym=True, errors='default', strict=True)
                    # Build combinations with tones
                    import itertools as _it
                    tone_combos = [' '.join(items) for items in _it.product(*tone_syllables)]
                    # Group by base
                    bases_order, base_to_variants = group_tone_variants_by_base(tone_combos)
                    grouped_pinyin = [', '.join(base_to_variants[b]) for b in bases_order]
                    grouped_georgian = [map_pinyin_to_georgian(b) for b in bases_order]
                    # Use grouped main/others if available
                    if grouped_pinyin:
                        main_base = remove_pinyin_tone_marks(grouped_pinyin[0].split(',')[0])
                        georgian_result = grouped_georgian[0]
                        other_bases = [remove_pinyin_tone_marks(x.split(',')[0]) for x in grouped_pinyin[1:]]
                        other_georgians = grouped_georgian[1:]
                except Exception:
                    pass
            
            from collections import OrderedDict
            result = OrderedDict()
            result['ქართული'] = {
                'pinyin': main_base,
                'other_pinyin': other_bases,
                'other_georgian': other_georgians,
                'ქართული': georgian_result
            }
            if include_tones and grouped_pinyin and grouped_georgian:
                result['ქართული']['grouped_pinyin'] = grouped_pinyin
                result['ქართული']['grouped_georgian'] = grouped_georgian
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
    app.run(debug=True, port=8080, host='0.0.0.0') 