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
    # Ensure case-insensitive mapping by lowercasing
    plain_syllables = [s.lower() for s in plain_syllables]
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


def ensure_georgian_vowel_end(text: str) -> str:
    """Append 'ი' if the Georgian transliteration does not end with a vowel.

    Checks the last non-space character. Used for non-special cases only.
    """
    if not text:
        return text
    stripped = text.rstrip()
    if not stripped:
        return text
    vowels = set('აეიოუ')
    return stripped if stripped[-1] in vowels else stripped + '-ი'


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


# ---------------- Georgian script conversion ----------------
GEORGIAN_MKHEDRULI_START = 0x10D0  # ა
GEORGIAN_ASOMTAVRULI_START = 0x10A0  # Ⴀ
GEORGIAN_NUSKHURI_START = 0x2D00  # ⴀ

def is_mkhedruli(ch: str) -> bool:
    cp = ord(ch)
    return 0x10D0 <= cp <= 0x10FF

def is_asomtavruli(ch: str) -> bool:
    cp = ord(ch)
    return 0x10A0 <= cp <= 0x10CF

def is_nuskhuri(ch: str) -> bool:
    cp = ord(ch)
    return 0x2D00 <= cp <= 0x2D2F

def convert_georgian_char(ch: str, target: str) -> str:
    cp = ord(ch)
    # Determine source base and index; assume aligned ordering across blocks
    if is_mkhedruli(ch):
        idx = cp - GEORGIAN_MKHEDRULI_START
    elif is_asomtavruli(ch):
        idx = cp - GEORGIAN_ASOMTAVRULI_START
    elif is_nuskhuri(ch):
        idx = cp - GEORGIAN_NUSKHURI_START
    else:
        return ch

    # Some codepoints in these ranges are not letters; guard typical range
    if idx < 0 or idx > 0x5F:
        return ch

    if target == 'mkhedruli':
        return chr(GEORGIAN_MKHEDRULI_START + idx)
    if target == 'asomtavruli':
        return chr(GEORGIAN_ASOMTAVRULI_START + idx)
    if target == 'nuskhuri':
        return chr(GEORGIAN_NUSKHURI_START + idx)
    return ch

def detect_georgian_script(text: str) -> str | None:
    for ch in text:
        if is_mkhedruli(ch):
            return 'mkhedruli'
        if is_asomtavruli(ch):
            return 'asomtavruli'
        if is_nuskhuri(ch):
            return 'nuskhuri'
    return None

def convert_georgian_scripts(text: str):
    source = detect_georgian_script(text) or 'mkhedruli'
    targets = [t for t in ['mkhedruli','asomtavruli','nuskhuri'] if t != source]
    result = {}
    for t in targets:
        converted = ''.join(convert_georgian_char(ch, t) for ch in text)
        result[f'to_{t}'] = converted
    result['source'] = source
    return result


# ---------------- Georgian → Latin (Mkhedruli transliteration) ----------------
GEORGIAN_TO_LATIN_MAP = {
    'ა': 'a', 'ბ': 'b', 'გ': 'g', 'დ': 'd', 'ე': 'e', 'ვ': 'v', 'ზ': 'z',
    'ჱ': 'ē', 'თ': 't', 'ი': 'i', 'კ': "k'", 'ლ': 'l', 'მ': 'm', 'ნ': 'n',
    'ჲ': 'y', 'ო': 'o', 'პ': "p'", 'ჟ': 'zh', 'რ': 'r', 'ს': 's', 'ტ': "t'",
    'ჳ': 'w', 'უ': 'u', 'ფ': 'p', 'ქ': 'k', 'ღ': 'gh', 'ყ': "q'", 'შ': 'sh',
    'ჩ': 'ch', 'ც': 'ts', 'ძ': 'dz', 'წ': "ts'", 'ჭ': "ch'", 'ხ': 'kh',
    'ჴ': 'ẖ', 'ჯ': 'j', 'ჰ': 'h', 'ჵ': 'ō', 'ჶ': 'f', 'ჷ': 'ȳ', 'ჸ': 'ʔ',
    'ჹ': 'ĝ', 'ჺ': 'ʕ', 'ჼ': 'n', 'ჾ': 'y', 'ჿ': 'w',
}

def normalize_to_mkhedruli(text: str) -> str:
    return ''.join(convert_georgian_char(ch, 'mkhedruli') for ch in text)

def transliterate_georgian_to_latin(text: str) -> str:
    mkh = normalize_to_mkhedruli(text)
    return ''.join(GEORGIAN_TO_LATIN_MAP.get(ch, ch) for ch in mkh)


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
        show_case_suffix = bool(data.get('show_case_suffix', True))
        input_language = data.get('input_language', 'chinese')
        geo_target = data.get('geo_target')

        if not text:
            return {'error': 'Please enter some text.\nგთხოვთ შეიყვანოთ ტექსტი.'}

        # Special cases (fixed Georgian names)
        special_cases = {
            "北京": "პეკინი",
            "南京": "ნანკინი",
            "陕西": "შაანსი",
            "香港": "ჰონგკონგი",
            "澳门": "მაკაო",
            "西藏": "ტიბეტი",
            "乌鲁木齐": "ურუმჩი",
            "孙中山": "სუნ იატსენი",
            "蒋介石": "ჩან კაიში",
            "李小龙": "ბრუს ლი",
            "成龙": "ჯეკი ჩანი",
            "成吉思汗": "ჩინგიზ-ყაენი",
            "忽必烈": "ყუბილაი",
            "孔子": "კონფუცი",
        }
        
        # We compute pinyin dynamically for special cases; no static overrides needed.

        has_chinese = contains_cjk(text)

        # Georgian script conversion path (do not touch Chinese path)
        if input_language in ('geo_to_mkhedruli','geo_to_asomtavruli','geo_to_nuskhuri','geo_to_latin') or input_language == 'georgian':
            # Single-target conversion (legacy modes or unified georgian + geo_target)
            if input_language == 'georgian':
                target = geo_target if geo_target in ('mkhedruli','asomtavruli','nuskhuri','latin') else 'mkhedruli'
            else:
                target = {
                    'geo_to_mkhedruli': 'mkhedruli',
                    'geo_to_asomtavruli': 'asomtavruli',
                    'geo_to_nuskhuri': 'nuskhuri',
                    'geo_to_latin': 'latin',
                }[input_language]
            source = detect_georgian_script(text) or 'mkhedruli'
            if target == 'latin':
                converted = transliterate_georgian_to_latin(text)
                return {"georgian_scripts": {"source": source, "to_latin": converted}}
            else:
                converted = ''.join(convert_georgian_char(ch, target) for ch in text)
                return {
                    "georgian_scripts": {
                        "source": source,
                        f"to_{target}": converted
                    }
                }

        # If user typed Pinyin, check if it matches any special Chinese phrase
        if not has_chinese:
            normalized_input = remove_pinyin_tone_marks(text.lower())
            normalized_input = re.sub(r"\s+", " ", normalized_input).strip()
            compact_input = normalized_input.replace(" ", "")

            matched_special = None
            for zh_phrase, geo_name in special_cases.items():
                # Build no-tone pinyin (single reading) for the special phrase
                py_no_tone_syllables = pypinyin.pinyin(
                    zh_phrase, style=pypinyin.Style.NORMAL, heteronym=False
                )
                py_no_tone = ' '.join(s[0] for s in py_no_tone_syllables if s and s[0]).lower()
                py_no_tone_compact = py_no_tone.replace(' ', '')

                if normalized_input == py_no_tone or compact_input == py_no_tone_compact:
                    matched_special = zh_phrase
                    break

            if matched_special is not None:
                # Choose pinyin to display (respect tone toggle)
                style = pypinyin.Style.TONE if include_tones else pypinyin.Style.NORMAL
                py_syllables = pypinyin.pinyin(matched_special, style=style, heteronym=False)
                single_pinyin = ' '.join(s[0] for s in py_syllables if s and s[0])
                if not include_tones:
                    single_pinyin = remove_pinyin_tone_marks(single_pinyin)

                translit_georgian = map_pinyin_to_georgian(remove_pinyin_tone_marks(single_pinyin))
                if show_case_suffix:
                    translit_georgian = ensure_georgian_vowel_end(translit_georgian)

                return {
                    "special": {
                        "pinyin": single_pinyin,
                        "other_pinyin": [],
                        "ქართული": special_cases[matched_special],
                        "other_georgian": [],
                        "translit_georgian": translit_georgian
                    }
                }

        # Special-case override for Chinese input
        if text in special_cases:
            # For special cases, show the predefined Georgian name and compute single pinyin
            style = pypinyin.Style.TONE if include_tones else pypinyin.Style.NORMAL
            py_syllables = pypinyin.pinyin(text, style=style, heteronym=False)
            single_pinyin = ' '.join(s[0] for s in py_syllables if s and s[0])
            if not include_tones:
                single_pinyin = remove_pinyin_tone_marks(single_pinyin)

            translit_georgian = map_pinyin_to_georgian(remove_pinyin_tone_marks(single_pinyin))
            if show_case_suffix:
                translit_georgian = ensure_georgian_vowel_end(translit_georgian)

            return {
                "special": {
                    "pinyin": single_pinyin,
                    "other_pinyin": [],
                    "ქართული": special_cases[text],
                    "other_georgian": [],
                    "translit_georgian": translit_georgian
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
            if show_case_suffix:
                georgian_variants = [ensure_georgian_vowel_end(g) for g in georgian_variants]
            georgian_variants = deduplicate_preserve_order(georgian_variants)
        else:
            georgian_variants = [map_pinyin_to_georgian(v) for v in grouped_variants]
            if show_case_suffix:
                georgian_variants = [ensure_georgian_vowel_end(g) for g in georgian_variants]
            georgian_variants = deduplicate_preserve_order(georgian_variants)

        return {
            "ქართული": {
                "pinyin": grouped_variants[0] if grouped_variants else "",
                "other_pinyin": grouped_variants[1:] if len(grouped_variants) > 1 else [],
                "ქართული": georgian_variants[0] if georgian_variants else "",
                "other_georgian": georgian_variants[1:] if len(georgian_variants) > 1 else [],
                "grouped_pinyin": grouped_variants if include_tones else None,
                "grouped_georgian": georgian_variants if include_tones else None
            }
        }

    except Exception as e:
        return {"error": str(e)}


# ---------------- Flask routes ----------------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/newversionforgeorgian')
def index_new_georgian():
    return render_template('index-new.html')


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
