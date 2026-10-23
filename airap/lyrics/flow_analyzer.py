"""Flow and cadence analyzer for rap lyrics.

Provides:
- Syllable counting for English words, Chinese characters, and Romanized Pinyin.
- Flow cadence analysis (density, boom_bap, trap_triplet, chopper_fast).
- Rhyme scheme detection (end rhymes, internal rhymes, multisyllabic rhymes).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


class CadenceType(str, Enum):
    BOOM_BAP = "boom_bap"
    TRAP_TRIPLET = "trap_triplet"
    CHOPPER_FAST = "chopper_fast"


# ============================================================================
# Phonetic & Rhyme Dictionaries
# ============================================================================

# Chinese 13 Standard Rhyme Families (十三辙 / 嘻哈韵部)
CHINESE_RHYME_GROUPS: Dict[str, str] = {
    "ang": (
        "光狂王床帮网强亮上唱枪荡装创放长望港掌浪扬样相想向响伤黄皇脏降江阳房忙"
        "庞堂藏场当常章康帮梁方郎唐芒量刚罡丧殃桑张章防盲妨商荒粮苍榜访仓汤奖航翔"
        "朗廊抗扛邦纲冈钢秧"
    ),
    "eng": (
        "风梦中东动痛通红重送空声生争情明冰定命听行晴星醒镜境清请领迎龙从层灯朋"
        "同峰精英赢成盛称整正政城胜登衡增名冷腾横争兵精形倾停敬病灵营警碰荣蒙翁"
        "影英应鹰景井精京警晶睛峰封丰疯朋棚膨能僧层冷坑崩盟猛萌盲恒亨庚更更"
    ),
    "an": (
        "天看慢办变站散战玩面线片电见连点钱难感段穿船关专转算短满伴盘前现念间简"
        "单乱赚链岸边原尖言全险圈完选眼染展犯惨斩坛毯班斑般半赶乾反饭范干换欢款"
        "剑倩渐见现显练恋变片简剪剑建健件间鉴潜签前浅钱纤鲜仙先泉源圆远愿院暖断"
    ),
    "en": (
        "真神人门深分很本身跟根轮魂尘准温问吻进近心信新金今尽紧亲琴林民军寻训群"
        "音春纯存论尊吞孙奔痕沉任针陈根奔盆喷纷芬痕恨狠沉审枕晨衬臣身申伸参深慎"
    ),
    "ai": (
        "快带拍白来开摆买海在怪爱帅踩坏态赛牌台百拜摘拆排柴财裁外盖害哀耐筛呆彩"
        "开代迈害概待彩载再裁矮赖牌脉代带待怠殆改害凯慨概乃奶耐晒筛态苔抬塞腮赛"
    ),
    "ei": (
        "给飞黑谁水北回雷美妹内杯推追归贵对退味泪累随醉灰位规配培陪非肥废匪倍被"
        "妹内威维伟微围未唯未危吹锤垂炊脆翠催粹费废沸匪累垒泪类佩配沛培危微为违"
    ),
    "ao": (
        "到叫跳靠老跑道告照笑掉暴高号套脑超刀朝桥妙考保报抱宝标料聊潮焦敲雕草早"
        "造搞扰炒爪劳敲描表耀教飘标掉包毛淘操傲奥堡饱抱豹操草吵炒导岛倒刀高稿搞"
    ),
    "ou": (
        "头狗手走够后口收肉球求秀透楼游秋流留久九酒友有休救投漏修偷丢钩受厚抖抽"
        "首守某偶柔搜筹楼欧谋扣优悠愁仇钩狗苟垢后厚侯喉走奏揍搜艘叟首剖剖谋浮否"
    ),
    "i": (
        "你起几期比李里力气器米底弟第低地一七洗戏急及极集笔毙离立历皮披体提替题"
        "西席密秘机击诗事世是十日词死子字自次刺逼滴基骑迷衣梯疑意泥低立寄息夕习"
        "系析系戏替洗希批基鸡击急即季寄寂挤技纪计义议易异逆泥拟你尼迷弥谜米密秘"
    ),
    "u": (
        "不出步哭苦酷读独堵肚土突途图路录入怒木目物母五无舞武雾树术书数熟处初粗"
        "住主注猪触促足族阻租祖顾故孤估骨服赋负富副度杜户湖虎呼互古主楚谱塑毒突"
        "屋铺幕木母互如儒乳入捕布步部赋附副负富妇库裤酷哭窟鲁路露陆录芦怒努努"
    ),
    "a": (
        "发花画家加假拉啦吧把爸妈马打大达搭拿擦差茶查沙杀傻耍刷话滑抓下夏辖爬卡"
        "夸垮答怕砸踏杂它蜡爸发沙法霸塌杀卡八巴拔把靶霸擦差插达打大发伐法乏嘎哈"
    ),
    "o": (
        "我多过国活火伙错做作昨座脱落罗说握阔破默磨抹博伯波播歌哥格各核合喝河客"
        "刻热特车澈扯遮这者设社得德盒特课策何折科渴克苛割各格合核盒何河褐核革隔"
    ),
    "ie": (
        "别接结节姐街夜叶野业界月乐雪绝决确缺写血鞋谢邪携解界介借铁贴烈猎劣切且"
        "跌爹斜灭帖窃页野切捷叠蔑折歇携挟契砌劣猎列裂烈猎猎咩撇叠贴列冽烈猎贴铁"
    ),
}

# Build fast reverse lookup for Chinese characters
CHAR_TO_CHINESE_RHYME: Dict[str, str] = {}
for _group, _chars in CHINESE_RHYME_GROUPS.items():
    for _ch in _chars:
        CHAR_TO_CHINESE_RHYME[_ch] = _group

# Common English rap rhyming rimes
ENGLISH_RHYME_DICTIONARY: Dict[str, str] = {
    # -ow / -o / -oe
    "flow": "OW", "glow": "OW", "blow": "OW", "show": "OW", "go": "OW",
    "know": "OW", "pro": "OW", "slow": "OW", "throw": "OW", "grow": "OW",
    "low": "OW", "snow": "OW", "row": "OW", "toe": "OW", "woe": "OW",
    "foe": "OW", "bro": "OW", "yo": "OW", "no": "OW", "so": "OW",
    # -eet / -eat / -ite
    "beat": "EET", "street": "EET", "heat": "EET", "meet": "EET", "feet": "EET",
    "sweet": "EET", "elite": "EET", "repeat": "EET", "defeat": "EET", "cheat": "EET",
    "sheet": "EET", "treat": "EET", "fleet": "EET", "greet": "EET", "neat": "EET",
    # -in
    "in": "IN", "skin": "IN", "spin": "IN", "win": "IN", "twin": "IN",
    "pin": "IN", "chin": "IN", "bin": "IN", "sin": "IN", "thin": "IN",
    "begin": "IN", "within": "IN", "grin": "IN",
    # -it
    "spit": "IT", "hit": "IT", "lit": "IT", "bit": "IT", "fit": "IT",
    "quit": "IT", "split": "IT", "sit": "IT", "pit": "IT", "kit": "IT",
    "admit": "IT", "commit": "IT", "legit": "IT",
    # -ip
    "trip": "IP", "drip": "IP", "grip": "IP", "flip": "IP", "rip": "IP",
    "dip": "IP", "ship": "IP", "skip": "IP", "strip": "IP", "tip": "IP",
    "clip": "IP", "whip": "IP",
    # -ime
    "rhyme": "AYM", "time": "AYM", "climb": "AYM", "prime": "AYM", "crime": "AYM",
    "sublime": "AYM", "dime": "AYM", "slime": "AYM", "chime": "AYM",
    # -ire
    "fire": "AYER", "higher": "AYER", "desire": "AYER", "wire": "AYER",
    "inspire": "AYER", "tire": "AYER", "sire": "AYER", "admire": "AYER",
    # -op
    "drop": "OP", "pop": "OP", "stop": "OP", "top": "OP", "cop": "OP",
    "hop": "OP", "hip-hop": "OP", "shop": "OP", "crop": "OP", "prop": "OP",
    # -ap
    "rap": "AP", "trap": "AP", "clap": "AP", "snap": "AP", "map": "AP",
    "cap": "AP", "slap": "AP", "tap": "AP", "gap": "AP", "wrap": "AP",
    "scrap": "AP", "strap": "AP",
    # -ack
    "track": "ACK", "back": "ACK", "black": "ACK", "stack": "ACK",
    "attack": "ACK", "crack": "ACK", "pack": "ACK", "smack": "ACK", "jack": "ACK",
    # -ame
    "game": "EYM", "flame": "EYM", "name": "EYM", "fame": "EYM",
    "claim": "EYM", "shame": "EYM", "aim": "EYM", "tame": "EYM", "same": "EYM",
    # -ain / -ane
    "pain": "EYN", "rain": "EYN", "train": "EYN", "brain": "EYN",
    "lane": "EYN", "insane": "EYN", "chain": "EYN", "gain": "EYN",
    "main": "EYN", "plane": "EYN", "drain": "EYN", "reign": "EYN",
    # -ound
    "sound": "OUND", "ground": "OUND", "round": "OUND", "pound": "OUND",
    "bound": "OUND", "found": "OUND", "hound": "OUND", "underground": "OUND",
    # -own
    "down": "OWN", "town": "OWN", "crown": "OWN", "brown": "OWN", "clown": "OWN",
    # -otion
    "motion": "OHSHUN", "potion": "OHSHUN", "notion": "OHSHUN", "devotion": "OHSHUN",
    "emotion": "OHSHUN", "locomotion": "OHSHUN",
    # -ight / -ite
    "night": "AYT", "light": "AYT", "tight": "AYT", "right": "AYT",
    "fight": "AYT", "sight": "AYT", "white": "AYT", "ignite": "AYT",
    "bite": "AYT", "site": "AYT", "flight": "AYT", "bright": "AYT", "mic": "IK",
    # -ing
    "king": "ING", "ring": "ING", "sing": "ING", "wing": "ING", "swing": "ING",
    "bring": "ING", "thing": "ING", "string": "ING",
    # -ill
    "kill": "ILL", "skill": "ILL", "chill": "ILL", "drill": "ILL",
    "fill": "ILL", "spill": "ILL", "will": "ILL", "still": "ILL", "thrill": "ILL",
    # -ash
    "cash": "ASH", "flash": "ASH", "smash": "ASH", "clash": "ASH",
    "crash": "ASH", "dash": "ASH", "blast": "AST", "fast": "AST", "past": "AST",
    # -one
    "zone": "OHN", "tone": "OHN", "bone": "OHN", "phone": "OHN", "alone": "OHN",
    "stone": "OHN", "throne": "OHN", "clone": "OHN",
    # -ool
    "cool": "OOL", "school": "OOL", "fool": "OOL", "rule": "OOL", "tool": "OOL",
}

# Number words syllable counts (0-20, 30, 40, etc.)
NUMBER_SYLLABLES: Dict[str, int] = {
    "0": 2, "1": 1, "2": 1, "3": 1, "4": 1, "5": 1, "6": 1, "7": 2, "8": 1, "9": 1,
    "10": 1, "11": 3, "12": 1, "13": 2, "14": 2, "15": 2, "16": 2, "17": 3, "18": 2,
    "19": 2, "20": 2, "24": 3, "30": 2, "40": 2, "50": 2, "60": 2, "70": 3, "80": 2,
    "90": 2, "100": 2, "808": 3,
}

# English word syllable overrides for common rap vocabulary
ENGLISH_SYLLABLE_OVERRIDES: Dict[str, int] = {
    "the": 1, "a": 1, "an": 1, "to": 1, "of": 1, "in": 1, "on": 1, "at": 1,
    "rap": 1, "flow": 1, "rhyme": 1, "rhymes": 1, "rhythm": 2, "spit": 1,
    "beat": 1, "beats": 1, "mic": 1, "triplet": 2, "triplets": 2,
    "chopper": 2, "underground": 3, "cadence": 2, "syllable": 3, "syllables": 3,
    "fire": 1, "higher": 2, "desire": 3, "boom": 1, "bap": 1,
    "every": 2, "people": 2, "different": 2, "business": 2,
    "family": 3, "memory": 3, "champion": 3, "motion": 2, "potion": 2,
    "studio": 3, "freestyle": 2, "homie": 2, "hustle": 2, "muscle": 2,
    "yeah": 1, "yo": 1, "uh": 1, "snare": 1, "bass": 1, "bars": 1, "bar": 1,
}


# ============================================================================
# Dataclasses
# ============================================================================

@dataclass
class FlowCadence:
    cadence_type: str  # 'boom_bap', 'trap_triplet', 'chopper_fast'
    syllables_per_bar: int
    syllables_per_beat: float
    syllables_per_second: float
    bpm: float = 130.0
    triplet_ratio: float = 0.0
    description: str = ""

    @property
    def syllable_count(self) -> int:
        return self.syllables_per_bar

    def to_dict(self) -> dict:
        return {
            "cadence_type": self.cadence_type,
            "syllables_per_bar": self.syllables_per_bar,
            "syllables_per_beat": round(self.syllables_per_beat, 3),
            "syllables_per_second": round(self.syllables_per_second, 3),
            "bpm": self.bpm,
            "triplet_ratio": round(self.triplet_ratio, 3),
            "description": self.description,
        }


@dataclass
class InternalRhyme:
    word1: str
    word2: str
    bar_index: int
    positions: Tuple[int, int]
    rhyme_key: str

    def to_dict(self) -> dict:
        return {
            "word1": self.word1,
            "word2": self.word2,
            "bar_index": self.bar_index,
            "positions": list(self.positions),
            "rhyme_key": self.rhyme_key,
        }


@dataclass
class MultisyllabicRhyme:
    phrase1: str
    phrase2: str
    bar1_index: int
    bar2_index: int
    syllable_count: int
    pattern: List[str]

    def to_dict(self) -> dict:
        return {
            "phrase1": self.phrase1,
            "phrase2": self.phrase2,
            "bar1_index": self.bar1_index,
            "bar2_index": self.bar2_index,
            "syllable_count": self.syllable_count,
            "pattern": self.pattern,
        }


@dataclass
class RhymeSchemeResult:
    pattern: str  # e.g. "AABB", "ABAB", "AAAA"
    rhyme_groups: Dict[str, List[int]]  # label -> bar indices [0, 1]
    rhyme_density: float  # Percentage of bars participating in a rhyme
    end_rhymes: List[Dict[str, str]] = field(default_factory=list)
    multisyllabic_rhymes: List[MultisyllabicRhyme] = field(default_factory=list)
    internal_rhymes: List[InternalRhyme] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "pattern": self.pattern,
            "rhyme_groups": self.rhyme_groups,
            "rhyme_density": round(self.rhyme_density, 3),
            "end_rhymes": self.end_rhymes,
            "multisyllabic_rhymes": [m.to_dict() for m in self.multisyllabic_rhymes],
            "internal_rhymes": [ir.to_dict() for ir in self.internal_rhymes],
        }


@dataclass
class FlowAnalysisResult:
    bars_count: int
    total_syllables: int
    average_density_per_bar: float
    average_density_per_second: float
    dominant_cadence: str
    bar_cadences: List[FlowCadence]
    rhyme_scheme: RhymeSchemeResult

    def to_dict(self) -> dict:
        return {
            "bars_count": self.bars_count,
            "total_syllables": self.total_syllables,
            "average_density_per_bar": round(self.average_density_per_bar, 2),
            "average_density_per_second": round(self.average_density_per_second, 2),
            "dominant_cadence": self.dominant_cadence,
            "bar_cadences": [c.to_dict() for c in self.bar_cadences],
            "rhyme_scheme": self.rhyme_scheme.to_dict(),
        }


# ============================================================================
# Core Functions: Syllable Counting
# ============================================================================

def is_chinese_char(c: str) -> bool:
    """Check if character is CJK Unified Ideograph."""
    return any(
        "\u4e00" <= c <= "\u9fff"
        or "\u3400" <= c <= "\u4dbf"
        or "\uf900" <= c <= "\ufaff"
        for _ in [None]
    )


def strip_accents(text: str) -> str:
    """Normalize text and remove diacritics / tone marks."""
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def count_syllables_chinese(text: str) -> int:
    """Count Chinese character syllables (1 character = 1 syllable)."""
    return sum(1 for c in text if is_chinese_char(c))


def count_syllables_english(word: str) -> int:
    """Accurately count syllables in an English word or token."""
    w = word.lower().strip()
    if not w:
        return 0

    # Digits check
    clean_digits = re.sub(r"[^\d]", "", w)
    if clean_digits:
        if clean_digits in NUMBER_SYLLABLES:
            return NUMBER_SYLLABLES[clean_digits]
        # Fallback for digits: 1 syllable per digit (rough estimate)
        return len(clean_digits)

    # Word overrides
    if w in ENGLISH_SYLLABLE_OVERRIDES:
        return ENGLISH_SYLLABLE_OVERRIDES[w]

    # Clean punctuation
    w_clean = re.sub(r"[^a-z]", "", strip_accents(w))
    if not w_clean:
        return 0
    if w_clean in ENGLISH_SYLLABLE_OVERRIDES:
        return ENGLISH_SYLLABLE_OVERRIDES[w_clean]
    if len(w_clean) <= 3:
        return 1

    # Vowel sequence counting
    vowel_clusters = re.findall(r"[aeiouy]+", w_clean)
    count = len(vowel_clusters)

    # Silent 'e' adjustment
    if w_clean.endswith("e") and not w_clean.endswith(("ee", "oe", "ye")):
        # e.g. bottle, simple (consonant + le)
        if w_clean.endswith("le") and len(w_clean) > 2 and w_clean[-3] not in "aeiouy":
            pass
        else:
            count -= 1
    elif w_clean.endswith("ed"):
        if not w_clean.endswith(("ted", "ded")):
            count -= 1
    elif w_clean.endswith("es"):
        if not w_clean.endswith(("ces", "ses", "zes", "xes", "shes", "ches", "ges")):
            count -= 1

    return max(1, count)


def count_syllables(text: str) -> int:
    """Count total syllables in a string supporting English, Chinese, and Pinyin.

    Mixed strings (e.g. 'Check我的麦克风 flow') are seamlessly analyzed.
    """
    if not text:
        return 0

    total = 0
    current_latin: List[str] = []

    for char in text:
        if is_chinese_char(char):
            if current_latin:
                total += count_syllables_english("".join(current_latin))
                current_latin = []
            total += 1
        elif char.isalnum() or char in "'’":
            current_latin.append(char)
        else:
            if current_latin:
                total += count_syllables_english("".join(current_latin))
                current_latin = []

    if current_latin:
        total += count_syllables_english("".join(current_latin))

    return total


def tokenize_lyrics(text: str) -> List[str]:
    """Tokenize lyrics preserving Chinese characters as individual words and splitting Latin tokens."""
    tokens: List[str] = []
    current_latin: List[str] = []

    for c in text:
        if is_chinese_char(c):
            if current_latin:
                tokens.append("".join(current_latin))
                current_latin = []
            tokens.append(c)
        elif c.isalnum() or c in "'’":
            current_latin.append(c)
        else:
            if current_latin:
                tokens.append("".join(current_latin))
                current_latin = []

    if current_latin:
        tokens.append("".join(current_latin))
    return tokens


# ============================================================================
# Core Functions: Rhyme Analysis
# ============================================================================

def get_pinyin_rhyme_group(pinyin_str: str) -> Optional[str]:
    """Map a Latin Pinyin final to standard Chinese rhyme group."""
    s = strip_accents(pinyin_str.lower().strip())
    # Longest finals first
    if s.endswith(("uang", "iang", "ang")):
        return "ang"
    if s.endswith(("iong", "ong", "eng", "ing")):
        return "eng"
    if s.endswith(("uan", "ian", "uan", "an")):
        return "an"
    if s.endswith(("un", "in", "en")):
        return "en"
    if s.endswith(("uai", "ai")):
        return "ai"
    if s.endswith(("ui", "ei")):
        return "ei"
    if s.endswith(("iao", "ao")):
        return "ao"
    if s.endswith(("iu", "ou")):
        return "ou"
    if s.endswith(("ie", "ue", "ve")):
        return "ie"
    if s.endswith(("ua", "ia", "a")):
        return "a"
    if s.endswith(("uo", "o", "e")):
        return "o"
    if s.endswith("u"):
        return "u"
    if s.endswith(("i", "er")):
        return "i"
    return None


def get_rhyme_key(word: str) -> str:
    """Extract phonetic rhyme key for an English word or Chinese character.

    Words with the same rhyme key are considered rhyming.
    """
    clean_raw = word.strip().lower()
    if not clean_raw:
        return ""

    # If it is a Chinese character
    if len(clean_raw) == 1 and is_chinese_char(clean_raw):
        if clean_raw in CHAR_TO_CHINESE_RHYME:
            return f"ZH_{CHAR_TO_CHINESE_RHYME[clean_raw].upper()}"
        return f"ZH_{clean_raw}"

    # If it ends with a Chinese character (e.g. multi-char Chinese word like '飞翔')
    if is_chinese_char(clean_raw[-1]):
        last_char = clean_raw[-1]
        if last_char in CHAR_TO_CHINESE_RHYME:
            return f"ZH_{CHAR_TO_CHINESE_RHYME[last_char].upper()}"
        return f"ZH_{last_char}"

    # Strip diacritics for Pinyin or English
    w = strip_accents(clean_raw)
    w_alpha = re.sub(r"[^a-z]", "", w)
    if not w_alpha:
        return ""

    # Check English Rhyme Dictionary first
    if w_alpha in ENGLISH_RHYME_DICTIONARY:
        return ENGLISH_RHYME_DICTIONARY[w_alpha]

    # Check for tone marks (explicit Pinyin) or unambiguous Pinyin syllables
    has_tone = clean_raw != w
    unambiguous_pinyin = {
        "zhuang", "shuang", "chuang", "kuang", "guang", "huang", "jiang", "qiang", "xiang",
        "zhong", "chong", "shong", "xiong", "qiong", "feng", "geng", "keng", "heng",
        "zheng", "cheng", "sheng", "reng", "biao", "piao", "miao", "diao", "tiao", "niao",
        "liao", "jiao", "qiao", "xiao", "kuai", "guai", "huai", "zhuan", "chuan", "shuan",
        "xuan", "yuan", "quan", "juan", "tian", "dian", "xian", "qian", "jian", "bian",
        "pian", "mian", "lian", "nian", "zhao", "chao", "shao", "zhou", "chou", "shou",
        "chun", "shun", "zhun", "xue", "yue", "que", "jue", "bie", "pie", "mie", "die", "tie"
    }

    if has_tone or w_alpha in unambiguous_pinyin:
        pinyin_group = get_pinyin_rhyme_group(w_alpha)
        if pinyin_group:
            return f"ZH_{pinyin_group.upper()}"

    # Heuristic English Rhyme Extraction
    if w_alpha.endswith("ight"):
        return "AYT"
    if w_alpha.endswith(("tion", "sion")):
        return "OHSHUN"
    if w_alpha.endswith("ing"):
        return "ING"

    # Silent 'e' pattern (e.g. 'flame', 'prime')
    silent_e_match = re.search(r"([aeiouy])([^aeiouy]+)e$", w_alpha)
    if silent_e_match:
        vowel, consonant = silent_e_match.groups()
        return f"{vowel.upper()}_{consonant.upper()}"

    # Extract last vowel sequence + remaining consonants
    match = re.search(r"([aeiouy]+[^aeiouy]*)$", w_alpha)
    if match:
        return match.group(1).upper()

    return w_alpha[-3:].upper()


def detect_rhyme_scheme(bars: List[str]) -> RhymeSchemeResult:
    """Detect end rhyme scheme (e.g. 'AABB', 'ABAB', 'ABBA', 'AAAA') across a list of bars."""
    if not bars:
        return RhymeSchemeResult(pattern="", rhyme_groups={}, rhyme_density=0.0)

    end_tokens: List[str] = []
    rhyme_keys: List[str] = []

    for bar in bars:
        tokens = tokenize_lyrics(bar)
        if tokens:
            end_word = tokens[-1]
            end_tokens.append(end_word)
            rhyme_keys.append(get_rhyme_key(end_word))
        else:
            end_tokens.append("")
            rhyme_keys.append("")

    # Assign scheme letters (A, B, C, ...)
    key_to_letter: Dict[str, str] = {}
    letters: List[str] = []
    next_letter_idx = 0
    rhyme_groups: Dict[str, List[int]] = {}

    for i, key in enumerate(rhyme_keys):
        if not key:
            letters.append("X")
            continue

        if key not in key_to_letter:
            letter = chr(ord("A") + next_letter_idx)
            next_letter_idx += 1
            key_to_letter[key] = letter
        else:
            letter = key_to_letter[key]

        letters.append(letter)
        rhyme_groups.setdefault(letter, []).append(i)

    # Calculate rhyme density (fraction of bars belonging to groups of size >= 2)
    rhyming_bar_count = sum(len(indices) for indices in rhyme_groups.values() if len(indices) >= 2)
    density = rhyming_bar_count / max(1, len(bars))

    end_rhyme_details = [
        {"bar": i, "word": end_tokens[i], "key": rhyme_keys[i], "tag": letters[i]}
        for i in range(len(bars))
    ]

    pattern = "".join(letters)
    return RhymeSchemeResult(
        pattern=pattern,
        rhyme_groups=rhyme_groups,
        rhyme_density=density,
        end_rhymes=end_rhyme_details,
    )


def detect_internal_rhymes(bars: List[str]) -> List[InternalRhyme]:
    """Detect rhymes occurring within the same bar or between content words of adjacent bars."""
    stop_words: Set[str] = {
        "the", "a", "an", "to", "of", "in", "on", "at", "by", "for", "with",
        "and", "or", "is", "it", "my", "your", "i", "you", "he", "she", "we", "they",
        "me", "us", "him", "her", "that", "this", "so", "as", "if", "no", "not",
        "我", "你", "他", "她", "它", "的", "了", "在", "是", "有", "和", "就", "不", "人", "都", "一"
    }

    internal_rhymes: List[InternalRhyme] = []

    for bar_idx, bar in enumerate(bars):
        tokens = tokenize_lyrics(bar)
        if len(tokens) < 2:
            continue

        # Look for intra-bar rhymes (within the same bar)
        word_info: List[Tuple[int, str, str]] = []
        for pos, tok in enumerate(tokens):
            clean_tok = tok.lower()
            if clean_tok in stop_words or len(clean_tok) < 2:
                continue
            key = get_rhyme_key(tok)
            if key:
                word_info.append((pos, tok, key))

        # Check all pairs in bar
        for i in range(len(word_info)):
            for j in range(i + 1, len(word_info)):
                pos1, tok1, key1 = word_info[i]
                pos2, tok2, key2 = word_info[j]
                if key1 == key2 and tok1.lower() != tok2.lower():
                    internal_rhymes.append(
                        InternalRhyme(
                            word1=tok1,
                            word2=tok2,
                            bar_index=bar_idx,
                            positions=(pos1, pos2),
                            rhyme_key=key1,
                        )
                    )

    return internal_rhymes


def detect_multisyllabic_rhymes(
    bars: List[str], min_syllables: int = 2
) -> List[MultisyllabicRhyme]:
    """Detect multisyllabic (compound/mosaic) rhymes between bars (default min 2 syllables)."""
    multis: List[MultisyllabicRhyme] = []
    if len(bars) < 2:
        return multis

    bar_syllables: List[List[Tuple[str, str]]] = []
    # Each item: list of (syllable_unit_text, rhyme_coda) for the tail of each bar

    for bar in bars:
        tokens = tokenize_lyrics(bar)
        bar_units: List[Tuple[str, str]] = []
        for tok in tokens:
            # If Chinese character
            if is_chinese_char(tok):
                key = get_rhyme_key(tok)
                bar_units.append((tok, key))
            else:
                # English word
                syll_count = count_syllables_english(tok)
                key = get_rhyme_key(tok)
                bar_units.append((tok, key))
        bar_syllables.append(bar_units)

    # Compare adjacent and near bars (within window of 4 bars)
    for i in range(len(bars)):
        for j in range(i + 1, min(i + 5, len(bars))):
            units_i = bar_syllables[i]
            units_j = bar_syllables[j]
            if not units_i or not units_j:
                continue

            # Compare suffixes from tail backwards
            match_len = 0
            pattern: List[str] = []
            words_i: List[str] = []
            words_j: List[str] = []

            max_check = min(len(units_i), len(units_j), 6)
            for k in range(1, max_check + 1):
                u_i = units_i[-k]
                u_j = units_j[-k]
                if u_i[1] == u_j[1] and u_i[1]:  # Same rhyme key
                    match_len += 1
                    pattern.insert(0, u_i[1])
                    words_i.insert(0, u_i[0])
                    words_j.insert(0, u_j[0])
                else:
                    break

            total_syllables = sum(count_syllables(w) for w in words_i)
            if match_len >= min_syllables or total_syllables >= min_syllables:
                multis.append(
                    MultisyllabicRhyme(
                        phrase1=" ".join(words_i),
                        phrase2=" ".join(words_j),
                        bar1_index=i,
                        bar2_index=j,
                        syllable_count=total_syllables,
                        pattern=pattern,
                    )
                )

    return multis


# ============================================================================
# Core Functions: Flow Cadence Analysis
# ============================================================================

def classify_cadence(
    syllable_count: int, beats: float = 4.0, bpm: float = 130.0
) -> FlowCadence:
    """Classify flow cadence into 'boom_bap', 'trap_triplet', or 'chopper_fast'.

    Criteria:
    - chopper_fast: >= 16 syllables/bar (>= 4.0 syllables/beat, rapid 16th/32nd chopper notes)
    - trap_triplet: 12-15 syllables/bar (3.0 - 3.75 syllables/beat, triplet cadence feel)
    - boom_bap: < 12 syllables/bar (< 3.0 syllables/beat, steady pocket, 90s classic bounce)
    """
    beats = max(1.0, beats)
    bpm = max(1.0, bpm)
    bar_duration = beats * (60.0 / bpm)

    syllables_per_beat = syllable_count / beats
    syllables_per_sec = syllable_count / bar_duration

    # Triplet ratio estimation (closeness to multiples of 3 per beat)
    mod3 = syllable_count % 3
    triplet_ratio = 1.0 - (mod3 / 3.0)

    if syllable_count >= 16 or syllables_per_beat >= 4.0:
        c_type = CadenceType.CHOPPER_FAST.value
        desc = "Fast chopper cadence with high syllable density and rapid delivery."
    elif 12 <= syllable_count <= 15 or (3.0 <= syllables_per_beat < 4.0):
        c_type = CadenceType.TRAP_TRIPLET.value
        desc = "Trap triplet cadence with rhythmic 3-syllable bounce per beat."
    else:
        c_type = CadenceType.BOOM_BAP.value
        desc = "Boom bap pocket cadence with steady, rhythmic 90s groove."

    return FlowCadence(
        cadence_type=c_type,
        syllables_per_bar=syllable_count,
        syllables_per_beat=syllables_per_beat,
        syllables_per_second=syllables_per_sec,
        bpm=bpm,
        triplet_ratio=triplet_ratio,
        description=desc,
    )


def analyze_flow(bars: List[str], bpm: float = 130.0) -> FlowAnalysisResult:
    """Analyze the complete flow cadence and rhyme architecture for a verse."""
    if not bars:
        empty_scheme = RhymeSchemeResult(pattern="", rhyme_groups={}, rhyme_density=0.0)
        return FlowAnalysisResult(
            bars_count=0,
            total_syllables=0,
            average_density_per_bar=0.0,
            average_density_per_second=0.0,
            dominant_cadence=CadenceType.BOOM_BAP.value,
            bar_cadences=[],
            rhyme_scheme=empty_scheme,
        )

    bar_cadences: List[FlowCadence] = []
    total_syllables = 0

    for bar_text in bars:
        s_count = count_syllables(bar_text)
        total_syllables += s_count
        cadence = classify_cadence(s_count, beats=4.0, bpm=bpm)
        bar_cadences.append(cadence)

    avg_bar = total_syllables / len(bars)
    seconds_per_bar = 4.0 * (60.0 / bpm)
    avg_sec = (total_syllables / (len(bars) * seconds_per_bar)) if seconds_per_bar > 0 else 0.0

    # Determine dominant cadence
    cadence_counts: Dict[str, int] = {}
    for c in bar_cadences:
        cadence_counts[c.cadence_type] = cadence_counts.get(c.cadence_type, 0) + 1
    dominant = max(cadence_counts.items(), key=lambda kv: kv[1])[0]

    # Rhyme scheme and internal rhymes
    rhyme_result = detect_rhyme_scheme(bars)
    rhyme_result.internal_rhymes = detect_internal_rhymes(bars)
    rhyme_result.multisyllabic_rhymes = detect_multisyllabic_rhymes(bars)

    return FlowAnalysisResult(
        bars_count=len(bars),
        total_syllables=total_syllables,
        average_density_per_bar=avg_bar,
        average_density_per_second=avg_sec,
        dominant_cadence=dominant,
        bar_cadences=bar_cadences,
        rhyme_scheme=rhyme_result,
    )


# ============================================================================
# FlowAnalyzer Class Wrapper
# ============================================================================

class FlowAnalyzer:
    """Flow and Cadence Analysis Engine for AIRapStudio."""

    def __init__(self, default_bpm: float = 130.0):
        self.default_bpm = default_bpm

    def count_syllables(self, text: str) -> int:
        return count_syllables(text)

    def count_syllables_english(self, word: str) -> int:
        return count_syllables_english(word)

    def count_syllables_chinese(self, text: str) -> int:
        return count_syllables_chinese(text)

    def get_rhyme_key(self, word: str) -> str:
        return get_rhyme_key(word)

    def classify_cadence(
        self, syllable_count: int, beats: float = 4.0, bpm: Optional[float] = None
    ) -> FlowCadence:
        return classify_cadence(
            syllable_count, beats=beats, bpm=bpm or self.default_bpm
        )

    def detect_rhyme_scheme(self, bars: List[str]) -> RhymeSchemeResult:
        res = detect_rhyme_scheme(bars)
        res.internal_rhymes = detect_internal_rhymes(bars)
        res.multisyllabic_rhymes = detect_multisyllabic_rhymes(bars)
        return res

    def detect_internal_rhymes(self, bars: List[str]) -> List[InternalRhyme]:
        return detect_internal_rhymes(bars)

    def detect_multisyllabic_rhymes(
        self, bars: List[str], min_syllables: int = 2
    ) -> List[MultisyllabicRhyme]:
        return detect_multisyllabic_rhymes(bars, min_syllables=min_syllables)

    def analyze_verse(
        self, bars: List[str], bpm: Optional[float] = None
    ) -> FlowAnalysisResult:
        return analyze_flow(bars, bpm=bpm or self.default_bpm)
