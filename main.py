from flask import Flask, render_template, request, jsonify
import pypinyin
import re
import itertools
from pypinyin_dict.pinyin_data import kxhc1983
from flask_cors import CORS
import unicodedata
import whisper
import tempfile
import os
import ssl
import urllib.request
# Load the pinyin data
kxhc1983.load()

app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "*"}})

# Load Whisper model once when app starts
whisper_model = None
try:
    print("Loading Whisper model...")
    
    # Create an SSL context that doesn't verify certificates (for downloading)
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    # Set the SSL context for urllib
    urllib.request.install_opener(urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl_context)))
    
    whisper_model = whisper.load_model("base")
    print("Whisper model loaded successfully!")
    
except Exception as e:
    print(f"Warning: Could not load Whisper model: {e}")
    print("Speech-to-text functionality will be disabled, but translation will work fine.")
    whisper_model = None

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
        # Get the single input text
        text = data.get('text', '').strip()
        
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
        
        # Check if input contains Chinese characters
        has_chinese = bool(re.search(r'[\u4e00-\u9fa5]', text))
        
        if has_chinese:
            # Handle Chinese input
            # Check for special cases first
            if text in special_cases:
                prof_pinyin = get_professional_pinyin(text)
                return {"special": {"pinyin": prof_pinyin, "ქართული": special_cases[text]}}
            
            # Regular Chinese processing
            text_pinyin = get_pinyin([text])
            text_georgian = get_georgian(text_pinyin)
            
            from collections import OrderedDict
            result = OrderedDict()
            text_prof_pinyin = get_professional_pinyin(text)
            result['ქართული'] = {
                'pinyin': text_prof_pinyin,
                'ქართული': ' '.join(text_georgian.values())
            }
            return result
        else:
            # Handle pinyin input (convert to lowercase for consistency)
            text = text.lower()
            
            # Check special case for pinyin
            def match_special(pinyin):
                for hanzi, geo in special_cases.items():
                    special_pinyin = get_professional_pinyin(hanzi)
                    if pinyin.replace(' ', '').lower() == special_pinyin.replace(' ', '').lower():
                        return geo
                return None
            
            from collections import OrderedDict
            result = OrderedDict()
            geo = match_special(text)
            georgian = geo or map_pinyin_to_georgian(text)
            result['ქართული'] = {
                'pinyin': text,
                'ქართული': georgian
            }
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

@app.route('/speech-to-text', methods=['POST', 'OPTIONS'])
def speech_to_text():
    if request.method == 'OPTIONS':
        return '', 200
    
    # Check if Whisper model is available
    if whisper_model is None:
        return jsonify({
            'error': 'Speech-to-text is currently unavailable. Whisper model failed to load.'
        }), 503
    
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400
        
        audio_file = request.files['audio']
        
        if audio_file.filename == '':
            return jsonify({'error': 'No audio file selected'}), 400
        
        # Create temporary file for audio
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
            audio_file.save(temp_file.name)
            
            try:
                # Transcribe using Whisper
                print("Transcribing audio...")
                result = whisper_model.transcribe(temp_file.name, language="zh")
                transcribed_text = result['text'].strip()
                
                print(f"Transcribed: {transcribed_text}")
                
                if not transcribed_text:
                    return jsonify({'error': 'No speech detected in audio'}), 400
                
                return jsonify({
                    'text': transcribed_text,
                    'language': result.get('language', 'zh')
                })
                
            except Exception as e:
                print(f"Whisper transcription error: {str(e)}")
                return jsonify({'error': f'Transcription failed: {str(e)}'}), 500
            
            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_file.name)
                except:
                    pass
    
    except Exception as e:
        app.logger.error(f"Error in speech_to_text: {str(e)}")
        return jsonify({'error': str(e)}), 500

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