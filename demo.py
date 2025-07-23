import tkinter as tk
from tkinter import messagebox
import pypinyin
import re
import itertools

# Load the pinyin data
from pypinyin_dict.pinyin_data import kxhc1983
kxhc1983.load()

# Convert each character of the word into pinyin(pinyin_list):
# eg.'乐山'-pinyin_list：['le shan', 'yue shan']
def get_pinyin(words):
    # Because a Chinese character has multiple possible pinyin, the results are presented in the form of a list of combinations of different pinyin.
    pinyin_list = []

    for word in words:
        for char in word:
            pinyin_result = pypinyin.pinyin(char, style=0, heteronym=True)
            pinyin_list.append(pinyin_result)

    # Combine the different possible pinyins of each word(pinyin_list) in the form of a Cartesian product：
    # eg.'乐山'-all_result: ['le shan', 'yue shan']
    all_result = []
    pinyin_list = [item[0] for item in pinyin_list]
    pinyin_cartesian = list(itertools.product(*pinyin_list))

    # replace the 'v' in the pinyin(pinyin_cartesian) with 'ü'
    all_result = [' '.join(pinyin).replace('v', 'ü') for pinyin in pinyin_cartesian]

    return all_result

# Convert each pinyin of the characters into Georgian(pinyin_list):
# eg.'乐山'-all_result：{'le shan': 'ლე შან', 'yue shan': 'იუე შან'}
def get_georgian(pinyin_list):
    # The input content is a list. When we transcribe Pinyin to Georgian, the result are presented in the form of a dictionary,
    # in which each value of the list, that is, Pinyin, is used as the primary key,
    # while its corresponding Georgian transcription as the value of the primary key.
    all_result = {}
    for pinyin in pinyin_list:
        # There are three layers of conversion logic.
        # The first layer is fixed letter clusters,
        # including letter clusters with inconsistent letter digits, such as two pinyin letters converted to one Georgian letter,
        # and other fixed letter clusters, which are converted to Georgian at the first layer.
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

        # The second layer is the letter clusters with specific conditions.
        # There are some sound changes cases with special pronunciations under specific conditions,
        # which is presented here as conditional sentences with "if".
        text_long = re.sub(r'(?<=[jqxy])u', 'iu', text_long)
        if 'iuan' in text_long and 'g' not in text_long[text_long.index('iuan')+3:]:
            text_long = text_long.replace('iuan', 'iuen')
        if 'ian' in text_long:
            text_long = text_long.replace('ian', 'ien')

        # The third layer is fixed single letters,
        # which will be converted from a pinyin letter to one or more Georgian letters.
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

# Convert function
def convert(data):
    first_name = data.get('first_name', '')
    last_name = data.get('last_name', '')
    others = data.get('others', '')

    # Define special cases and their corresponding consequences
    special_cases = {
        "北京": "პეკინი (პეიძინგ)",
        "南京": "ნანკინი (ნანძინგ)",
        "陕西": "შაანსი (შანსი)",
        "香港": "ჰონგკონგი (სიანგკანგ)",
        "澳门": "მაკაო (აომენ)",
        "西藏": "ტიბეტი (სიწანგ)",
        "乌鲁木齐": "ურუმჩი (ულუმუცი)",
        "中山孙": "სუნ იატსენი (სუნ ჭუნგშან)",
        "介石蒋": "ჩან კაიში (ძიანგ ძიეში)",
        "小龙李": "ბრუს ლი (ლი სიაოლუნგ)",
        "成龙": "ჯეკი ჩანი (ჩენგ ლუნგ)",
        "成吉思汗": "ჩინგიზ-ყაენი (ჩენგძისხან)",
        "忽必烈": "ყუბილაი (ხუპილიე)",
        "孔子": "კონფუცი (ქუნგწი)",
    };

    # Check if a special case is matched
    if others:
        special_case_key = others
    else:
        special_case_key = (first_name, last_name)

    if special_case_key in special_cases:
        return special_cases[special_case_key]
    
    # Checks if first_name, last_name, and others are empty strings
    if not bool(first_name) and not bool(last_name) and not bool(others):
        result = "All input fields are empty.\nყველა შეყვანის ნაწილი ცარიელია."
        return result

    # Check if there is no-chinese input
    if not (re.search(r'[\u4e00-\u9fa5]', first_name) or
            re.search(r'[\u4e00-\u9fa5]', last_name) or
            re.search(r'[\u4e00-\u9fa5]', others)):
        return "Please enter Chinese characters.\nგთხოვთ შეიყვანოთ ჩინური იეროგლიფი."

    try:
        # Processing Data
        # Using the function get_pinyin() to get the pinyin of three variables.
        first_name_pinyin = get_pinyin(first_name)
        last_name_pinyin = get_pinyin(last_name)
        others_pinyin = get_pinyin(others)

        # Using the function get_georgian() to get the gerogian conversion of three variables.
        first_name_georgian = get_georgian(first_name_pinyin)
        last_name_georgian = get_georgian(last_name_pinyin)
        others_georgian = get_georgian(others_pinyin)

        # Both last name and first name of gerogian conversion are dictionaries,
        # and the combination of the them is presented in the form of a Cartesian product,
        # that is, the Cartesian product of the primary key(pinyin)
        # and also the Cartesian product of the value(georgian conversion) corresponding to the primary key.
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

        # Conditions for returning results
        if bool(first_name) and bool(last_name):
            result = {'სახელი+გვარი': merged_dict_1, 'გვარი+სახელი': merged_dict_2}
        elif bool(first_name) and not bool(last_name):
            result = {'სახელი':first_name_georgian}
        elif not bool(first_name) and bool(last_name):
            result = {'გვარი':last_name_georgian}
        elif others_georgian:
            result = {'სახელი':others_georgian}
        else:
            result = "No valid input provided"
        
        return result
        
    except Exception as e:
        return str(e)

class ChineseGeorgianConvertor:
    def __init__(self, root):
        self.root = root
        self.root.title("Chinese-Georgian Convertor")

        # add title
        self.title_label = tk.Label(self.root, text="🇨🇳🇬🇪 ჩინურ-ქართული კონვერტორი", font=("Arial", 20, "bold"))
        self.title_label.pack(pady=20)

        # People's Name Frame
        self.people_frame = tk.LabelFrame(self.root, text="Personal Names / პირ.", padx=10, pady=10)
        self.people_frame.pack(padx=10, pady=10, fill="both", expand=True)

        self.first_name_label = tk.Label(self.people_frame, text="First Name / სახელი:")
        self.first_name_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.first_name_entry = tk.Entry(self.people_frame, width=30)
        self.first_name_entry.grid(row=0, column=1, padx=5, pady=5)

        self.last_name_label = tk.Label(self.people_frame, text="Last Name / გვარი:")
        self.last_name_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.last_name_entry = tk.Entry(self.people_frame, width=30)
        self.last_name_entry.grid(row=1, column=1, padx=5, pady=5)

        # Others Frame
        self.others_frame = tk.LabelFrame(self.root, text="Geographical Names and others / გეოგრ. და სხვა", padx=10, pady=10)
        self.others_frame.pack(padx=10, pady=10, fill="both", expand=True)

        self.others_label = tk.Label(self.others_frame, text="Name / სახელი:")
        self.others_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.others_entry = tk.Entry(self.others_frame, width=30)
        self.others_entry.grid(row=0, column=1, padx=5, pady=5)

        # Convert Button
        self.convert_button = tk.Button(self.root, text="Convert", command=self.convert)
        self.convert_button.pack(pady=10)

        # Result Frame
        self.result_frame = tk.LabelFrame(self.root, text="Result / შედეგი", padx=10, pady=10)
        self.result_frame.pack(padx=10, pady=10, fill="both", expand=True)

        self.result_text = tk.Text(self.result_frame, height=10, width=50)
        self.result_text.pack(padx=5, pady=5)

    def convert(self):
        first_name = self.first_name_entry.get()
        last_name = self.last_name_entry.get()
        others = self.others_entry.get()

        data = {
            "first_name": first_name,
            "last_name": last_name,
            "others": others
        }

        try:
            result = convert(data)
            if isinstance(result, dict):
                result_str = "\n".join([f"{key}: {value}" for key, value in result.items()])
            else:
                result_str = str(result)
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, result_str)
        except Exception as e:
            messagebox.showerror("Error", str(e))

if __name__ == "__main__":
    root = tk.Tk()
    app = ChineseGeorgianConvertor(root)
    root.mainloop()