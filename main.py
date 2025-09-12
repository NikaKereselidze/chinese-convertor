from flask import Flask, render_template, request, jsonify
import pypinyin
import re
import itertools
from pypinyin_dict.pinyin_data import ktghz2013
from flask_cors import CORS
import unicodedata
import os
import csv

# Load the pinyin data
ktghz2013.load()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ---------------- Security headers ----------------
@app.after_request
def add_security_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Content-Security-Policy'] = "frame-ancestors *"
    response.headers['X-Frame-Options'] = 'ALLOWALL'
    return response


# ---------------- Pinyin helpers ----------------
def get_pinyin(words, include_tones=False):
    style = pypinyin.Style.TONE if include_tones else pypinyin.Style.NORMAL
    pinyin_result = pypinyin.pinyin(words, style=style, heteronym=True)
    result_tuples = list(itertools.product(*pinyin_result))
    all_result = [' '.join(items) for items in result_tuples]
    return all_result


def remove_pinyin_tone_marks(pinyin_text):
    return ''.join(
        c for c in unicodedata.normalize('NFD', pinyin_text)
        if unicodedata.category(c) != 'Mn'
    )


def get_georgian(pinyin_list):
    if not pinyin_list:
        return {}

    all_result = {}
    for pinyin in pinyin_list:
        # long replacements first
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
        pinyin_clean = pinyin.replace(' ', '')

        all_result[pinyin_clean] = text_short

    return all_result


def map_pinyin_to_georgian(pinyin_str):
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


# ---------------- Polyphonic data loading ----------------
def contains_cjk(text: str) -> bool:
    """Return True if any char is in common CJK ranges (incl. extensions)."""
    for ch in text:
        cp = ord(ch)
        if (
            0x3400 <= cp <= 0x4DBF or
            0x4E00 <= cp <= 0x9FFF or
            0xF900 <= cp <= 0xFAFF or
            0x20000 <= cp <= 0x2A6DF or
            0x2A700 <= cp <= 0x2B73F or
            0x2B740 <= cp <= 0x2B81F or
            0x2B820 <= cp <= 0x2CEAF or
            0x2F800 <= cp <= 0x2FA1F
        ):
            return True
    return False


def load_polyphonic_data():
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
        return {}

    return mapping


POLYPHONIC_MAP = load_polyphonic_data()


def lookup_polyphonic_readings(text):
    """Lookup polyphonic readings for single char or multi-char phrase."""
    data = POLYPHONIC_MAP.get(text)
    if not data:
        return None
    readings = data.get('readings_list', [])
    if not readings:
        return None
    main = readings[0]
    others = readings[1:] if len(readings) > 1 else []
    return (main, others)


# ---------------- Conversion ----------------
def convert(data):
    try:
        text = data.get('text', '').strip()
        include_tones = bool(data.get('include_tones', False))

        if not text:
            return {'error': 'Please enter some text.\nგთხოვთ შეიყვანოთ ტექსტი.'}

        # Special cases
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
            "李小龙": "ბრუს ლი",
            "成龙": "ჯეკი ჩანი",
            "成吉思汗": "ჩინგიზ-ყაენი",
            "忽必烈": "ყუბილაი",
            "孔子": "კონფუცი",
        }

        has_chinese = contains_cjk(text)
        if not has_chinese:
            return {"error": "No Chinese text detected."}

        # Special-case override
        if text in special_cases:
            prof_pinyin = get_pinyin(text, include_tones)
            return {"special": {"pinyin": prof_pinyin, "ქართული": special_cases[text]}}

        # Polyphonic dictionary lookup (supports multi-char phrases too)
        polyphonic = lookup_polyphonic_readings(text)
        if polyphonic is not None:
            main_pinyin, other_pinyins = polyphonic
            variants = [main_pinyin] + other_pinyins
        else:
            # fallback: canonical reading
            variants = get_pinyin(text, include_tones)

        # Deduplicate
        variants = deduplicate_preserve_order(variants)

        # Georgian mapping
        georgian_variants = [map_pinyin_to_georgian(remove_pinyin_tone_marks(v)) for v in variants]

        return {
            "ქართული": {
                "pinyin": variants[0],
                "other_pinyin": variants[1:],
                "ქართული": georgian_variants[0],
                "other_georgian": georgian_variants[1:]
            }
        }

    except Exception as e:
        return {"error": str(e)}


# ---------------- Flask routes ----------------
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
        result = convert(data)
        return jsonify(result)
    except Exception as e:
        app.logger.error(f"Error in convert_endpoint: {str(e)}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=8080, host='0.0.0.0')
