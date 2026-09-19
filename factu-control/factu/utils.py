from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value) -> str:
    return hashlib.sha256(
        value if isinstance(value, bytes) else canonical(value).encode()
    ).hexdigest()


def clean(value) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFKC", str(value or ""))
        if unicodedata.category(c) != "Cf"
    ).strip()


def identifier(value) -> str:
    return re.sub(r"\s+", "", clean(value)).upper()


def money(value) -> Decimal:
    """Two decimal locales; reject ambiguous thousands-only strings, never guess."""
    if isinstance(value, (int, float, Decimal)):
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError("Importe no finito")
        return result
    s = re.sub(r"EUR|€|\s", "", clean(value), flags=re.I)
    if not re.fullmatch(r"[+-]?[0-9][0-9.,]*", s):
        raise ValueError(f"Importe inválido: {value!r}")
    if "," in s and "." in s:
        decimal, grouping = (",", ".") if s.rfind(",") > s.rfind(".") else (".", ",")
        left, right = s.rsplit(decimal, 1)
        if len(right) != 2 or not re.fullmatch(
            r"[+-]?\d{1,3}(?:" + re.escape(grouping) + r"\d{3})+", left
        ):
            raise ValueError("Separadores ambiguos")
        s = left.replace(grouping, "") + "." + right
    elif "," in s or "." in s:
        sep = "," if "," in s else "."
        if s.count(sep) != 1 or len(s.rsplit(sep, 1)[1]) not in (1, 2):
            raise ValueError("Separadores ambiguos")
        s = s.replace(sep, ".")
    try:
        result = Decimal(s)
    except InvalidOperation as exc:
        raise ValueError("Importe inválido") from exc
    if not result.is_finite():
        raise ValueError("Importe no finito")
    return result


# Fechas en letras: solo se reconoce lo que está en estas tablas. El patrón de
# captura del extractor se construye a partir de ellas, nunca con un comodín,
# para que una línea de prosa ("30 días desde la fecha de emisión") no pueda
# producir un candidato. Siete idiomas: los del lote 2.
LANGUAGES = ("es", "ca", "pt", "it", "fr", "de", "en")

_DAY_WORDS = {
    "es": "uno|primero|primer; dos|segundo; tres|tercero|tercer; cuatro|cuarto;"
    " cinco|quinto; seis|sexto; siete|séptimo; ocho|octavo; nueve|noveno;"
    " diez|décimo; once|undécimo; doce|duodécimo; trece|decimotercero;"
    " catorce|decimocuarto; quince|decimoquinto; dieciséis|decimosexto;"
    " diecisiete|decimoséptimo; dieciocho|decimoctavo; diecinueve|decimonoveno;"
    " veinte|vigésimo; veintiuno|vigésimo primero; veintidós|vigésimo segundo;"
    " veintitrés|vigésimo tercero; veinticuatro|vigésimo cuarto;"
    " veinticinco|vigésimo quinto; veintiséis|vigésimo sexto;"
    " veintisiete|vigésimo séptimo; veintiocho|vigésimo octavo;"
    " veintinueve|vigésimo noveno; treinta|trigésimo;"
    " treinta y uno|trigésimo primero",
    "ca": "u|un|primer; dos|segon; tres|tercer; quatre|quart; cinc|cinquè;"
    " sis|sisè; set|setè; vuit|vuitè; nou|novè; deu|desè; onze|onzè; dotze|dotzè;"
    " tretze|tretzè; catorze|catorzè; quinze|quinzè; setze|setzè; disset|dissetè;"
    " divuit|divuitè; dinou|dinovè; vint|vintè; vint-i-u|vint-i-un|vint-i-unè;"
    " vint-i-dos|vint-i-dosè; vint-i-tres|vint-i-tresè; vint-i-quatre|vint-i-quatrè;"
    " vint-i-cinc|vint-i-cinquè; vint-i-sis|vint-i-sisè; vint-i-set|vint-i-setè;"
    " vint-i-vuit|vint-i-vuitè; vint-i-nou|vint-i-novè; trenta|trentè;"
    " trenta-u|trenta-un|trenta-unè",
    "pt": "um|primeiro; dois|segundo; três|terceiro; quatro|quarto; cinco|quinto;"
    " seis|sexto; sete|sétimo; oito|oitavo; nove|nono; dez|décimo;"
    " onze|décimo primeiro; doze|décimo segundo; treze|décimo terceiro;"
    " catorze|quatorze|décimo quarto; quinze|décimo quinto;"
    " dezesseis|dezasseis|décimo sexto; dezessete|dezassete|décimo sétimo;"
    " dezoito|décimo oitavo; dezenove|dezanove|décimo nono; vinte|vigésimo;"
    " vinte e um|vigésimo primeiro; vinte e dois|vigésimo segundo;"
    " vinte e três|vigésimo terceiro; vinte e quatro|vigésimo quarto;"
    " vinte e cinco|vigésimo quinto; vinte e seis|vigésimo sexto;"
    " vinte e sete|vigésimo sétimo; vinte e oito|vigésimo oitavo;"
    " vinte e nove|vigésimo nono; trinta|trigésimo; trinta e um|trigésimo primeiro",
    "it": "uno|primo; due|secondo; tre|terzo; quattro|quarto; cinque|quinto;"
    " sei|sesto; sette|settimo; otto|ottavo; nove|nono; dieci|decimo;"
    " undici|undicesimo; dodici|dodicesimo; tredici|tredicesimo;"
    " quattordici|quattordicesimo; quindici|quindicesimo; sedici|sedicesimo;"
    " diciassette|diciassettesimo; diciotto|diciottesimo; diciannove|diciannovesimo;"
    " venti|ventesimo; ventuno|ventunesimo; ventidue|ventiduesimo;"
    " ventitré|ventitreesimo; ventiquattro|ventiquattresimo;"
    " venticinque|venticinquesimo; ventisei|ventiseiesimo;"
    " ventisette|ventisettesimo; ventotto|ventottesimo; ventinove|ventinovesimo;"
    " trenta|trentesimo; trentuno|trentunesimo",
    "fr": "un|premier; deux|deuxième|second; trois|troisième; quatre|quatrième;"
    " cinq|cinquième; six|sixième; sept|septième; huit|huitième; neuf|neuvième;"
    " dix|dixième; onze|onzième; douze|douzième; treize|treizième;"
    " quatorze|quatorzième; quinze|quinzième; seize|seizième;"
    " dix-sept|dix-septième; dix-huit|dix-huitième; dix-neuf|dix-neuvième;"
    " vingt|vingtième; vingt et un|vingt-et-un|vingt et unième;"
    " vingt-deux|vingt-deuxième; vingt-trois|vingt-troisième;"
    " vingt-quatre|vingt-quatrième; vingt-cinq|vingt-cinquième;"
    " vingt-six|vingt-sixième; vingt-sept|vingt-septième;"
    " vingt-huit|vingt-huitième; vingt-neuf|vingt-neuvième; trente|trentième;"
    " trente et un|trente-et-un|trente et unième",
    "de": "eins|ein|erste|ersten; zwei|zweite|zweiten; drei|dritte|dritten;"
    " vier|vierte|vierten; fünf|fünfte|fünften; sechs|sechste|sechsten;"
    " sieben|siebte|siebten|siebente|siebenten; acht|achte|achten;"
    " neun|neunte|neunten; zehn|zehnte|zehnten; elf|elfte|elften;"
    " zwölf|zwölfte|zwölften; dreizehn|dreizehnte|dreizehnten;"
    " vierzehn|vierzehnte|vierzehnten; fünfzehn|fünfzehnte|fünfzehnten;"
    " sechzehn|sechzehnte|sechzehnten; siebzehn|siebzehnte|siebzehnten;"
    " achtzehn|achtzehnte|achtzehnten; neunzehn|neunzehnte|neunzehnten;"
    " zwanzig|zwanzigste|zwanzigsten;"
    " einundzwanzig|einundzwanzigste|einundzwanzigsten;"
    " zweiundzwanzig|zweiundzwanzigste|zweiundzwanzigsten;"
    " dreiundzwanzig|dreiundzwanzigste|dreiundzwanzigsten;"
    " vierundzwanzig|vierundzwanzigste|vierundzwanzigsten;"
    " fünfundzwanzig|fünfundzwanzigste|fünfundzwanzigsten;"
    " sechsundzwanzig|sechsundzwanzigste|sechsundzwanzigsten;"
    " siebenundzwanzig|siebenundzwanzigste|siebenundzwanzigsten;"
    " achtundzwanzig|achtundzwanzigste|achtundzwanzigsten;"
    " neunundzwanzig|neunundzwanzigste|neunundzwanzigsten;"
    " dreißig|dreißigste|dreißigsten;"
    " einunddreißig|einunddreißigste|einunddreißigsten",
    "en": "one|first; two|second; three|third; four|fourth; five|fifth; six|sixth;"
    " seven|seventh; eight|eighth; nine|ninth; ten|tenth; eleven|eleventh;"
    " twelve|twelfth; thirteen|thirteenth; fourteen|fourteenth;"
    " fifteen|fifteenth; sixteen|sixteenth; seventeen|seventeenth;"
    " eighteen|eighteenth; nineteen|nineteenth; twenty|twentieth;"
    " twenty-one|twenty-first; twenty-two|twenty-second; twenty-three|twenty-third;"
    " twenty-four|twenty-fourth; twenty-five|twenty-fifth; twenty-six|twenty-sixth;"
    " twenty-seven|twenty-seventh; twenty-eight|twenty-eighth;"
    " twenty-nine|twenty-ninth; thirty|thirtieth; thirty-one|thirty-first",
}

_MONTH_WORDS = {
    "es": "enero; febrero; marzo; abril; mayo; junio; julio; agosto;"
    " septiembre|setiembre; octubre; noviembre; diciembre",
    "ca": "gener; febrer; març; abril; maig; juny; juliol; agost; setembre;"
    " octubre; novembre; desembre",
    "pt": "janeiro; fevereiro; março; abril; maio; junho; julho; agosto;"
    " setembro; outubro; novembro; dezembro",
    "it": "gennaio; febbraio; marzo; aprile; maggio; giugno; luglio; agosto;"
    " settembre; ottobre; novembre; dicembre",
    "fr": "janvier; février; mars; avril; mai; juin; juillet; août; septembre;"
    " octobre; novembre; décembre",
    "de": "januar; februar; märz; april; mai; juni; juli; august; september;"
    " oktober; november; dezember",
    "en": "january|jan; february|feb; march|mar; april|apr; may; june|jun;"
    " july|jul; august|aug; september|sep|sept; october|oct; november|nov;"
    " december|dec",
}

_YEAR_WORDS = {
    "es": "dos mil veinticuatro; dos mil veinticinco; dos mil veintiséis;"
    " dos mil veintisiete",
    "ca": "dos mil vint-i-quatre; dos mil vint-i-cinc; dos mil vint-i-sis;"
    " dos mil vint-i-set",
    "pt": "dois mil e vinte e quatro|dois mil vinte e quatro;"
    " dois mil e vinte e cinco|dois mil vinte e cinco;"
    " dois mil e vinte e seis|dois mil vinte e seis;"
    " dois mil e vinte e sete|dois mil vinte e sete",
    "it": "duemilaventiquattro; duemilaventicinque; duemilaventisei;"
    " duemilaventisette",
    "fr": "deux mille vingt-quatre; deux mille vingt-cinq; deux mille vingt-six;"
    " deux mille vingt-sept",
    "de": "zweitausendvierundzwanzig; zweitausendfünfundzwanzig;"
    " zweitausendsechsundzwanzig; zweitausendsiebenundzwanzig",
    "en": "two thousand twenty-four|two thousand and twenty-four;"
    " two thousand twenty-five|two thousand and twenty-five;"
    " two thousand twenty-six|two thousand and twenty-six;"
    " two thousand twenty-seven|two thousand and twenty-seven",
}


def fold(value: str) -> str:
    """Minúsculas, sin acentos y con espacios normalizados: solo para comparar."""
    text = unicodedata.normalize("NFD", clean(value).casefold().replace("ß", "ss"))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text.replace("’", "'")).strip()


def _table(source, start):
    numbers, forms = {}, set()
    for language, groups in source.items():
        for offset, group in enumerate(groups.split(";")):
            for word in group.split("|"):
                word = word.strip()
                key = fold(word)
                previous = numbers.get(key, (start + offset, frozenset()))
                if previous[0] != start + offset:
                    raise ValueError(f"Tabla de fechas ambigua: {word!r}")
                numbers[key] = (start + offset, previous[1] | {language})
                forms.update((word, key))
    return numbers, forms


_DAYS, _DAY_FORMS = _table(_DAY_WORDS, 1)
_MONTHS, _MONTH_FORMS = _table(_MONTH_WORDS, 1)
_YEARS, _YEAR_FORMS = _table(_YEAR_WORDS, 2024)


def _alternation(forms):
    return "|".join(re.escape(f) for f in sorted(forms, key=lambda w: (-len(w), w)))


_ARTICLE = r"(?:el|le|am|the|of|de|del|den)"
_ELISION = r"[dl]['’]"
_LEAD = rf"(?:{_ARTICLE}(?![\w'])[\s,]+|{_ELISION}[\s,]*)*"
_GAP = rf"(?:[\s,]+(?:{_ARTICLE}(?![\w'])[\s,]+)*|[\s,]*{_ELISION}[\s,]*)"


def _sequence(days, months, years):
    return (
        rf"{_LEAD}(?P<day>{days}|\d{{1,2}})(?![\w'])"
        rf"{_GAP}(?P<month>{months})(?![\w'])"
        rf"{_GAP}(?P<year>{years}|\d{{4}})(?![\w'])"
    )


# Para buscar sobre el texto literal del PDF (con acentos) y para comparar.
DATE_WORDS = _sequence(
    _alternation(_DAY_FORMS), _alternation(_MONTH_FORMS), _alternation(_YEAR_FORMS)
)
_DATE_WORDS_FOLDED = re.compile(
    _sequence(
        _alternation(_DAYS), _alternation(_MONTHS), _alternation(_YEARS)
    )
)


def _read_words(value):
    match = _DATE_WORDS_FOLDED.fullmatch(fold(value))
    if not match:
        return None
    day, day_languages = _DAYS.get(match["day"], (None, None))
    year, year_languages = _YEARS.get(match["year"], (None, None))
    month, languages = _MONTHS[match["month"]]
    for other in (day_languages, year_languages):
        if other and languages & other:
            languages &= other
    return (
        year if year is not None else int(match["year"]),
        month,
        day if day is not None else int(match["day"]),
        next(name for name in LANGUAGES if name in languages),
    )


def date_language(value: str):
    """Idioma de la tabla con la que se leyó una fecha en letras; None si no lo es."""
    read = _read_words(value)
    return read[3] if read else None


def invoice_date(value: str) -> str:
    s = clean(value)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    read = _read_words(s)
    if read:
        try:
            return date(read[0], read[1], read[2]).isoformat()
        except ValueError as exc:
            raise ValueError("Fecha ilegible o inválida") from exc
    raise ValueError("Fecha ilegible o inválida")


def iban_checksum(value: str) -> bool:
    s = identifier(value)
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", s):
        return False
    digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in s[4:] + s[:4])
    return int(digits) % 97 == 1
