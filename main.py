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
    if isinstance(pinyin_text, (list, tuple)):
        pinyin_text = ' '.join(pinyin_text)
    return ''.join(
        c for c in unicodedata.normalize('NFD', pinyin_text)
        if unicodedata.category(c) != 'Mn'
    )


def get_georgian(pinyin_list):
    if not pinyin_list:
        return {}

    all_result = {}
    for pinyin in pinyin_list:
        # Convert to lowercase for processing but keep original for result key
        pinyin_lower = pinyin.lower()
        
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
        text_long = re.sub(pattern, lambda match: replacements_long[match.group()], pinyin_lower, flags=re.IGNORECASE)

        text_long = re.sub(r'(?<=[jqxy])u', 'iu', text_long, flags=re.IGNORECASE)
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
        text_short = re.sub(pattern_short, lambda match: replacements_short[match.group()], text_long, flags=re.IGNORECASE)

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


def group_tone_variants_by_base(pinyin_list):
    """Group pinyin variants by their base (tone-less) form."""
    groups = {}
    for pinyin in pinyin_list:
        base = remove_pinyin_tone_marks(pinyin)
        if base not in groups:
            groups[base] = []
        groups[base].append(pinyin)
    
    # Return as list of comma-separated groups
    result = []
    for base, variants in groups.items():
        if len(variants) == 1:
            result.append(variants[0])
        else:
            result.append(', '.join(variants))
    return result


def group_by_base_with_order(pinyin_list):
    """Return (grouped_pinyin, base_order) preserving first-seen order by base.

    grouped_pinyin: list of strings where each string joins tone variants by comma
    base_order: list of tone-less base pinyins aligned with grouped_pinyin
    """
    groups = {}
    base_order = []
    for v in pinyin_list:
        base = remove_pinyin_tone_marks(v)
        if base not in groups:
            groups[base] = []
            base_order.append(base)
        groups[base].append(v)
    grouped = [', '.join(groups[b]) if len(groups[b]) > 1 else groups[b][0] for b in base_order]
    return grouped, base_order


def get_professional_pinyin(text, include_tones=False):
    """Get professional pinyin with heteronym support."""
    style = pypinyin.Style.TONE if include_tones else pypinyin.Style.NORMAL
    pinyin_result = pypinyin.pinyin(text, style=style, heteronym=True)
    result_tuples = list(itertools.product(*pinyin_result))
    all_result = [' '.join(items) for items in result_tuples]
    return all_result


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
            "蒋介石": "ჩან კაიში",
            "李小龙": "ბრუს ლი",
            "成龙": "ჯეკი ჩანი",
            "成吉思汗": "ჩინგიზ-ყაენი",
            "忽必烈": "ყუბილაი",
            "孔子": "კონფუცი",
        }

        has_chinese = contains_cjk(text)
    

        # Special-case override
        if text in special_cases:
            # For special cases, show the predefined Georgian name and a single pinyin reading
            style = pypinyin.Style.TONE if include_tones else pypinyin.Style.NORMAL
            py_syllables = pypinyin.pinyin(text, style=style, heteronym=False)
            single_pinyin = ' '.join(s[0] for s in py_syllables if s and s[0])
            if not include_tones:
                single_pinyin = remove_pinyin_tone_marks(single_pinyin)

            return {
                "special": {
                    "pinyin": single_pinyin,
                    "other_pinyin": [],
                    "ქართული": special_cases[text],
                    "other_georgian": []
                }
            }

        # Polyphonic dictionary lookup (supports multi-char phrases too)
        polyphonic = lookup_polyphonic_readings(text)
        if polyphonic is not None:
            main_pinyin, other_pinyins = polyphonic
            variants = [main_pinyin] + other_pinyins
        else:
            # fallback: use professional pinyin with heteronym support
            variants = get_professional_pinyin(text, include_tones)

        # Apply grouping/deduplication based on tone setting
        if include_tones:
            grouped_variants, base_order = group_by_base_with_order(variants)
        else:
            # Strip tones so tone variants collapse for single characters
            variants_no_tone = [remove_pinyin_tone_marks(v) for v in variants]
            grouped_variants = deduplicate_preserve_order(variants_no_tone)

        # Georgian mapping
        if include_tones:
            # Use base_order so each group maps to a single Georgian variant
            georgian_variants = [map_pinyin_to_georgian(b) for b in base_order]
            georgian_variants = deduplicate_preserve_order(georgian_variants)
        else:
            georgian_variants = [map_pinyin_to_georgian(v) for v in grouped_variants]
            georgian_variants = deduplicate_preserve_order(georgian_variants)

        return {
            "ქართული": {
                "pinyin": grouped_variants[0] if grouped_variants and has_chinese else "",
                "other_pinyin": grouped_variants[1:] if len(grouped_variants) > 1 and has_chinese else [],
                "ქართული": georgian_variants[0] if georgian_variants else "",
                "other_georgian": georgian_variants[1:] if len(georgian_variants) > 1 else [],
                "grouped_pinyin": grouped_variants if include_tones and has_chinese else None,
                "grouped_georgian": georgian_variants if include_tones else None
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
