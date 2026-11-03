"""One language policy for typed chat (and the same policy the voice instructions state).

Reply in the language and script of the traveller's latest message:

- English gets English.
- Hindi in Devanagari gets Hindi in Devanagari.
- Hindi written in Roman letters ("Hinglish") gets casual Roman-script Hinglish, not formal Hindi.
- A message with no clear signal ("12 December", "Goa", "2") keeps the language of the traveller's
  earlier messages, so a one-word answer never flips the conversation back to English.
- If the traveller switches language, the next reply switches with them.

Detection is plain code with word lists, no dependency and no model call. It is a hint, not a
verdict: the words a model writes are checked against it (`reply_fits_language`), and every fixed
sentence code writes comes from the catalog below in the same language. Place names, dates and
numbers are never translated here: they are filled into the sentences as given.
"""

import re
from collections.abc import Sequence
from typing import Literal

Language = Literal["en", "hi", "hinglish"]
LANGUAGES: tuple[Language, ...] = ("en", "hi", "hinglish")

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_WORDS = re.compile(r"[^\W\d_]+", re.UNICODE)

# Roman-script Hindi words that are not ordinary English words ("hi", "me", "to", "the" are left
# out on purpose). A word list is a heuristic; the model's own reading backs it up.
_HINGLISH_WORDS = frozenset(
    """mujhe mera meri mere hum hame humein aap aapka aapki tum tumhe hoon hai hain ho
    hoga hogi honge tha thi se ko ka ki ke par pe mein andar liye lie jana jaana jaa
    jaao jaoge jaunga jaungi jayenge chahiye chahta chahte chahti chahunga chahungi kya kab kahan
    kaha kaise kaisa kaisi kyun kyu kitna kitne kitni kaun konsa kaunsa ji
    aur ya bhi toh lekin magar abhi kal parso aaj subah shaam raat rahega rahenge rahegi karna
    karni karo karein kare karenge batao bataiye bataao bataiyega dikhao dikhaiye dekho dekhna
    chalo chaliye theek thik accha achha sahi galat bahut thoda zyada jyada kam sasta sasti
    mehenga mehengi saath akele wapas yahan wahan isse usse unka inka
    shukriya dhanyavad namaste yaar bhai thodi jayegi jayega milega milegi mil niklu niklun nikle
    nikalni dikha banao bana banado pehle pehla pichle pichla wale wala wali agle agla agli iska
    uska apna apni hamara hota hoti lagega lagegi padega rahe raha rahi sakta sakte sakti karunga
    karungi chalega chalegi kyunki isliye matlab bilkul ek teen chaar paanch chhe saat aath nau
    das lena lenge dena denge bolo bolna baat samjhao samjha batana bata dijiye kijiye""".split()
)
_ENGLISH_WORDS = frozenset(
    """the a an i is are was were am be been want wants wanted to from for my me we our you your
    please what how which when where why who can could would should will shall this that these
    those next with and or but not no yes trip travel travelling traveling go going need needs
    like people person one way round return flight flights train trains bus hotel hotels book
    cheap cheapest weather weekend day days night nights options option plan plans show tell
    about at on in of it its if so do does did have has had there here also just only""".split()
)


def _words(message: str) -> list[str]:
    return [word.casefold() for word in _WORDS.findall(message)]


def detect_language(message: str) -> Language | None:
    """The language of one message, or None when it gives no clear signal."""
    if _DEVANAGARI.search(message):
        return "hi"
    words = _words(message)
    hindi = sum(1 for word in words if word in _HINGLISH_WORDS)
    english = sum(1 for word in words if word in _ENGLISH_WORDS)
    if hindi and hindi >= english:
        return "hinglish"
    if english:
        return "en"
    return None


_ASKS_FOR_ENGLISH = re.compile(
    r"(?:in\s+english|english\s+(?:mein|me|main|please|pls)|speak\s+english|"
    r"english\s+bolo|english\s+mei)",
    re.IGNORECASE,
)
_ASKS_FOR_HINGLISH = re.compile(r"hinglish", re.IGNORECASE)
_ASKS_FOR_HINDI = re.compile(
    r"(?:in\s+hindi|hindi\s+(?:mein|me|main|bolo|please)|speak\s+hindi)", re.IGNORECASE
)
_ASKS_FOR_DEVANAGARI = re.compile(r"devanagari|देवनागरी|हिंदी\s*में|हिन्दी\s*में", re.IGNORECASE)


def requested_language(message: str) -> Language | None:
    """The language the traveller asked for in words ("explain in English", "Hinglish mein baat
    karo"), or None. A request wins over how the same message happens to be written.

    "Hindi" asked for in Roman letters is answered in Roman-script Hinglish, the way it was asked.
    Devanagari is used only when the traveller writes in it or names it.
    """
    if _ASKS_FOR_DEVANAGARI.search(message):
        return "hi"
    if _ASKS_FOR_ENGLISH.search(message):
        return "en"
    if _ASKS_FOR_HINGLISH.search(message):
        return "hinglish"
    if _ASKS_FOR_HINDI.search(message):
        return "hi" if _DEVANAGARI.search(message) else "hinglish"
    return None


def _language_of(message: str) -> Language | None:
    requested = requested_language(message)
    return requested if requested is not None else detect_language(message)


def resolve_language(message: str, earlier_traveller_messages: Sequence[str] = ()) -> Language:
    """The language to reply in: asked for, else this message's, else the most recent earlier one,
    else English."""
    found = _language_of(message)
    if found is not None:
        return found
    for earlier in reversed(earlier_traveller_messages):
        found = _language_of(earlier)
        if found is not None:
            return found
    return "en"


def reply_fits_language(text: str, language: Language) -> bool:
    """Whether a model's reply is plausibly in the language asked for. Used to reject a reply that
    ignored the policy; the caller then falls back to the catalog text, which always fits."""
    if language == "en":
        return not _DEVANAGARI.search(text)
    if language == "hi":
        return bool(_DEVANAGARI.search(text))
    if _DEVANAGARI.search(text):
        return False
    return any(word in _HINGLISH_WORDS for word in _words(text))


# -- the catalog of sentences code writes ---------------------------------------------------------
# {braces} are filled with the traveller's own values or code-made values, never translated.

_CATALOG: dict[str, dict[Language, str]] = {
    "q_origin": {
        "en": "Where will you be travelling from?",
        "hinglish": "Aap kahan se travel karenge?",
        "hi": "आप कहाँ से यात्रा करेंगे?",
    },
    "q_destination": {
        "en": "Where would you like to go?",
        "hinglish": "Aap kahan jana chahte hain?",
        "hi": "आप कहाँ जाना चाहते हैं?",
    },
    "q_departure_date": {
        "en": "Which date do you want to leave? Please give the day and month, for example "
        "12 December.",
        "hinglish": "Aap kis date ko nikalna chahte hain? Din aur mahina bata dijiye, jaise "
        "12 December.",
        "hi": "आप किस तारीख को निकलना चाहते हैं? कृपया दिन और महीना बताइए, जैसे 12 December।",
    },
    "q_trip_type": {
        "en": "Is this a one-way trip or a round trip?",
        "hinglish": "Yeh one-way trip hai ya round trip?",
        "hi": "यह वन-वे यात्रा है या राउंड ट्रिप?",
    },
    "q_return_date": {
        "en": "Which date will you come back? Please give the day and month, for example "
        "15 December.",
        "hinglish": "Aap kis date ko wapas aayenge? Din aur mahina bata dijiye, jaise 15 December.",
        "hi": "आप किस तारीख को वापस आएँगे? कृपया दिन और महीना बताइए, जैसे 15 December।",
    },
    "q_travellers": {
        "en": "How many people are travelling?",
        "hinglish": "Kitne log travel kar rahe hain?",
        "hi": "कितने लोग यात्रा कर रहे हैं?",
    },
    "empty": {
        "en": "I didn't catch that. Could you say it again?",
        "hinglish": "Mujhe samajh nahi aaya. Kya aap dobara bol sakte hain?",
        "hi": "मुझे समझ नहीं आया। क्या आप दोबारा बोल सकते हैं?",
    },
    "too_long": {
        "en": "That message was too long for me to read. Could you say it in a shorter way?",
        "hinglish": "Yeh message mere padhne ke liye bahut lamba hai. Kya aap ise chhota karke "
        "bata sakte hain?",
        "hi": "यह संदेश मेरे पढ़ने के लिए बहुत लंबा है। क्या आप इसे छोटा करके बता सकते हैं?",
    },
    "not_understood": {
        "en": "Sorry, I couldn't make sense of that just now. You can try again, or fill in "
        "the trip form instead.",
        "hinglish": "Maaf kijiye, abhi main yeh samajh nahi paaya. Aap dobara try kar sakte hain, "
        "ya trip form bhar sakte hain.",
        "hi": "क्षमा करें, मैं अभी यह समझ नहीं पाया। आप दोबारा कोशिश कर सकते हैं, या ट्रिप फ़ॉर्म भर सकते हैं।",
    },
    "okay": {"en": "Okay.", "hinglish": "Theek hai.", "hi": "ठीक है।"},
    "changed": {
        "en": "Okay, I changed the {field} from {old} to {new}.",
        "hinglish": "Theek hai, maine {field} {old} se badalkar {new} kar diya.",
        "hi": "ठीक है, मैंने {field} {old} से बदलकर {new} कर दिया।",
    },
    "hint_exact_date": {
        "en": "I need an exact date, not a phrase like “tomorrow”.",
        "hinglish": "Mujhe exact date chahiye, “kal” jaisa shabd nahi.",
        "hi": "मुझे सही तारीख चाहिए, “कल” जैसा शब्द नहीं।",
    },
    "max_days_ask": {
        "en": "I can plan up to {max_days} days at a time. How many days would you like?",
        "hinglish": "Main ek baar mein {max_days} din tak plan kar sakta hoon. Aap kitne din "
        "chahte hain?",
        "hi": "मैं एक बार में {max_days} दिन तक की योजना बना सकता हूँ। आप कितने दिन चाहते हैं?",
    },
    "max_days_kept": {
        "en": "I can plan up to {max_days} days at a time, so I kept {days} days.",
        "hinglish": "Main ek baar mein {max_days} din tak plan kar sakta hoon, isliye maine "
        "{days} din hi rakhe hain.",
        "hi": "मैं एक बार में {max_days} दिन तक की योजना बना सकता हूँ, इसलिए मैंने {days} दिन ही रखे हैं।",
    },
    "invalid_trip": {
        "en": "Those details don't make a valid trip. Could you check them?",
        "hinglish": "Yeh details ek valid trip nahi banate. Kya aap unhe check kar sakte hain?",
        "hi": "ये विवरण एक वैध यात्रा नहीं बनाते। क्या आप इन्हें जाँच सकते हैं?",
    },
    "invalid_itinerary": {
        "en": "Those details don't make a valid itinerary. Could you check them?",
        "hinglish": "Yeh details ek valid itinerary nahi banate. Kya aap unhe check kar sakte "
        "hain?",
        "hi": "ये विवरण एक वैध यात्रा-कार्यक्रम नहीं बनाते। क्या आप इन्हें जाँच सकते हैं?",
    },
    "year_note": {
        "en": "(I took the year as {years}.)",
        "hinglish": "(Maine saal {years} maana hai.)",
        "hi": "(मैंने वर्ष {years} माना है।)",
    },
    "ready": {
        "en": "Here is what I have: {summary}{note}. Is this right? Tell me anything you want "
        "to change.",
        "hinglish": "Mere paas yeh details hain: {summary}{note}. Kya yeh sahi hai? Kuch badalna "
        "ho to bata dijiye.",
        "hi": "मेरे पास ये विवरण हैं: {summary}{note}। क्या यह सही है? कुछ बदलना हो तो बता दीजिए।",
    },
    "confirm_dates": {
        "en": "I take “{phrase}” to mean leaving on {when}. Is that right? If you meant "
        "another day, tell me the exact date.",
        "hinglish": "Main “{phrase}” ka matlab {when} ko nikalna samajh raha hoon. Kya yeh sahi "
        "hai? Agar aap kisi aur din ki baat kar rahe the, to exact date bata dijiye.",
        "hi": "मैं “{phrase}” का मतलब {when} को निकलना समझ रहा हूँ। क्या यह सही है? अगर आप "
        "किसी और दिन की बात कर रहे थे, तो सही तारीख बता दीजिए।",
    },
    "today": {"en": "(today)", "hinglish": "(aaj)", "hi": "(आज)"},
    "dropped_pending": {
        "en": "I haven't used the date from your earlier phrase.",
        "hinglish": "Maine aapke pehle wale shabd se nikali hui date use nahi ki hai.",
        "hi": "मैंने आपके पहले वाले शब्द से निकाली गई तारीख़ का उपयोग नहीं किया है।",
    },
    "conflict_one_way": {
        "en": "You said one-way, but also gave a return date ({date}).",
        "hinglish": "Aapne one-way kaha, lekin return date ({date}) bhi di hai.",
        "hi": "आपने वन-वे कहा, लेकिन वापसी की तारीख ({date}) भी दी है।",
    },
    "conflict_return_before": {
        "en": "The return date is before the departure date.",
        "hinglish": "Return date departure date se pehle hai.",
        "hi": "वापसी की तारीख़ जाने की तारीख़ से पहले है।",
    },
    "which_right": {
        "en": "Which one is right?",
        "hinglish": "Inmein se kaun sahi hai?",
        "hi": "इनमें से कौन सा सही है?",
    },
    "cannot_book": {
        "en": "I can't book or take payments here. Booking is switched off, and nothing you say "
        "to me can book anything. I can help you plan the trip and compare options.",
        "hinglish": "Main yahan booking ya payment nahi kar sakta. Booking band hai, aur aapke "
        "kehne se bhi kuch book nahi hoga. Main trip plan karne aur options compare karne mein "
        "madad kar sakta hoon.",
        "hi": "मैं यहाँ बुकिंग या भुगतान नहीं कर सकता। बुकिंग बंद है, और आपके कहने से भी कुछ बुक "
        "नहीं होगा। मैं यात्रा की योजना बनाने और विकल्पों की तुलना करने में मदद कर सकता हूँ।",
    },
    "found": {
        "en": "Here is what I found:",
        "hinglish": "Mujhe yeh mila:",
        "hi": "मुझे यह मिला:",
    },
    "sample_footer": {
        "en": "These are sample (MOCK) results, not live prices or schedules.",
        "hinglish": "Yeh sample (MOCK) results hain, live prices ya schedule nahi.",
        "hi": "ये नमूना (MOCK) परिणाम हैं, लाइव कीमतें या समय-सारणी नहीं।",
    },
    "labels_footer": {
        "en": "Data source labels: {labels}.",
        "hinglish": "Data source labels: {labels}.",
        "hi": "डेटा स्रोत लेबल: {labels}।",
    },
    "traveller_cap": {
        "en": "This prototype handles up to {max_travellers} travellers. How many people are "
        "travelling?",
        "hinglish": "Yeh prototype {max_travellers} travellers tak handle karta hai. Kitne log "
        "travel kar rahe hain?",
        "hi": "यह प्रोटोटाइप {max_travellers} यात्रियों तक संभालता है। कितने लोग यात्रा कर रहे हैं?",
    },
    "small_greeting": {
        "en": "Hi! I'm TravelMate. I can help you plan a trip.",
        "hinglish": "Namaste! Main TravelMate hoon. Main aapki trip plan karne mein madad kar "
        "sakta hoon.",
        "hi": "नमस्ते! मैं TravelMate हूँ। मैं आपकी यात्रा की योजना बनाने में मदद कर सकता हूँ।",
    },
    "small_how_are_you": {
        "en": "I'm doing well, thank you for asking! I'm ready to help you plan a trip.",
        "hinglish": "Main theek hoon, shukriya! Batayiye, kis trip ke liye madad chahiye?",
        "hi": "मैं ठीक हूँ, धन्यवाद! बताइए, किस यात्रा के लिए मदद चाहिए?",
    },
    "small_thanks": {
        "en": "You're welcome!",
        "hinglish": "Aapka swagat hai!",
        "hi": "आपका स्वागत है!",
    },
    "small_goodbye": {
        "en": "Goodbye! Come back whenever you want to plan a trip.",
        "hinglish": "Alvida! Trip plan karni ho to wapas aaiyega.",
        "hi": "अलविदा! यात्रा की योजना बनानी हो तो फिर आइएगा।",
    },
}


def say(key: str, language: Language = "en", **values: object) -> str:
    """A fixed sentence in the given language, with the traveller's own values filled in."""
    return _CATALOG[key][language].format(**values)
