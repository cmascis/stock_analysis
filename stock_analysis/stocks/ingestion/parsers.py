"""BofA HTML parsing, adapted from the existing BofAStockAnalysis pipeline.

Pure parsing only: network, file writes, and checkpointing live in the runner.
"""

import re
import string
import urllib.parse

from bs4 import BeautifulSoup, NavigableString

STOCK_PATTERN = re.compile(
    "\\|\\s*(BUY|NEUTRAL|UNDERPERFORM|NO RATING)\\s*\\|\\s*([A-Z0-9./-]+\\s+[A-Z]+)\\s*\\|?"
)
MKT_CAP = "Mkt Cap:"
MKT_CAP_PATTERN = re.compile("([A-Za-z]{2,5})\\s*([\\d,]+(?:\\.\\d+)?)\\s*(mn|bn|k)?")
MKT_CAP_PATTERN_LINE1 = re.compile(
    "Mkt Cap:([A-Za-z]{2,5})\\s*([\\d,]+(?:\\.\\d+)?)\\s*(mn|bn|k)?"
)
MULTIPLIERS = {"k": 1000, "mn": 1000000, "bn": 1000000000}
CURRENCY_CODES = [
    "afn",
    "eur",
    "all",
    "dzd",
    "usd",
    "aoa",
    "xcd",
    "xad",
    "ars",
    "amd",
    "awg",
    "aud",
    "azn",
    "bsd",
    "bhd",
    "bdt",
    "bbd",
    "byn",
    "bzd",
    "xof",
    "bmd",
    "inr",
    "btn",
    "bob",
    "bov",
    "bam",
    "bwp",
    "nok",
    "brl",
    "bnd",
    "bgn",
    "bif",
    "cve",
    "khr",
    "xaf",
    "cad",
    "kyd",
    "clp",
    "clf",
    "cny",
    "cop",
    "cou",
    "kmf",
    "cdf",
    "nzd",
    "crc",
    "cup",
    "xcg",
    "czk",
    "dkk",
    "djf",
    "dop",
    "egp",
    "svc",
    "ern",
    "szl",
    "etb",
    "fkp",
    "fjd",
    "xpf",
    "gmd",
    "gel",
    "ghs",
    "gip",
    "gtq",
    "gbp",
    "gnf",
    "gyd",
    "htg",
    "hnl",
    "hkd",
    "huf",
    "isk",
    "idr",
    "xdr",
    "irr",
    "iqd",
    "ils",
    "jmd",
    "jpy",
    "jod",
    "kzt",
    "kes",
    "kpw",
    "krw",
    "kwd",
    "kgs",
    "lak",
    "lbp",
    "lsl",
    "zar",
    "lrd",
    "lyd",
    "chf",
    "mop",
    "mga",
    "mwk",
    "myr",
    "mvr",
    "mru",
    "mur",
    "xua",
    "mxn",
    "mxv",
    "mdl",
    "mnt",
    "mad",
    "mzn",
    "mmk",
    "nad",
    "npr",
    "nio",
    "ngn",
    "mkd",
    "omr",
    "pkr",
    "pab",
    "pgk",
    "pyg",
    "pen",
    "php",
    "pln",
    "qar",
    "ron",
    "rub",
    "rwf",
    "shp",
    "wst",
    "stn",
    "sar",
    "rsd",
    "scr",
    "sle",
    "sgd",
    "xsu",
    "sbd",
    "sos",
    "ssp",
    "lkr",
    "sdg",
    "srd",
    "sek",
    "che",
    "chw",
    "syp",
    "twd",
    "tjs",
    "tzs",
    "thb",
    "top",
    "ttd",
    "tnd",
    "try",
    "tmt",
    "ugx",
    "uah",
    "aed",
    "usn",
    "uyu",
    "uyi",
    "uyw",
    "uzs",
    "vuv",
    "ves",
    "ved",
    "vnd",
    "yer",
    "zmw",
    "zwg",
    "xba",
    "xbb",
    "xbc",
    "xbd",
    "xts",
    "xxx",
    "xau",
    "xpd",
    "xpt",
    "xag",
]


def sanitize_filename(s):
    """Remove characters that are not allowed in filenames."""
    s = s.replace(" ", "_")
    return re.sub("[^A-Za-z0-9_]", "", s)


def extract_subpage_links(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    subpage_links = []
    sections = soup.select(
        'section.portlet[id^="portlet_HtmlComponent_WAR_RLWebReportsportlet_INSTANCE_"]'
    )
    for section in sections:
        for a_tag in section.find_all("a", href=True):
            stockInfoLine = a_tag.find_next_sibling()
            if not stockInfoLine:
                continue
            stock_info = str(stockInfoLine.get_text(strip=True))
            match = STOCK_PATTERN.search(stock_info)
            if match:
                link_text = a_tag.get_text(strip=True)
                href = a_tag["href"]
                if link_text and href:
                    if not href.lower().startswith("http"):
                        continue
                    stock_dict = {}
                    ticker_symbol = match.group(2)
                    if ticker_symbol:
                        stock_dict["Ticker"] = ticker_symbol
                    rating = match.group(1)
                    if rating:
                        stock_dict["Rating"] = rating
                    cap_match = MKT_CAP_PATTERN_LINE1.search(stock_info)
                    if cap_match:
                        currency = cap_match.group(1).upper()
                        if currency:
                            stock_dict["Currency"] = currency
                        number_str = cap_match.group(2).replace(",", "")
                        if number_str:
                            number = float(number_str)
                            suffix = cap_match.group(3)
                            if suffix:
                                multiplier = MULTIPLIERS.get(suffix.lower(), 1)
                                if multiplier:
                                    number *= multiplier
                            stock_dict["Market_Cap"] = number
                            if stockInfoLine.find_parent("p"):
                                blurbline = stockInfoLine.find_parent(
                                    "p"
                                ).find_next_sibling()
                                if blurbline:
                                    blurb = str(blurbline.get_text(strip=True))
                                    stock_dict["Blurb"] = remove_weird_chars(blurb)
                    else:
                        mktCap = stockInfoLine.find_next_sibling()
                        notFoundCap = True
                        notFoundVal = True
                        while notFoundCap and mktCap:
                            mktCapInfo = str(mktCap.get_text(strip=True))
                            if MKT_CAP in mktCapInfo:
                                notFoundCap = False
                                mktCap = mktCap.find_next_sibling()
                                while notFoundVal and mktCap:
                                    mkCapInfo = str(mktCap.get_text(strip=True))
                                    cap_match = MKT_CAP_PATTERN.search(mkCapInfo)
                                    if cap_match:
                                        notFoundVal = False
                                        currency = cap_match.group(1).upper()
                                        if currency:
                                            stock_dict["Currency"] = currency
                                        number_str = cap_match.group(2).replace(",", "")
                                        if number_str:
                                            number = float(number_str)
                                            suffix = cap_match.group(3)
                                            if suffix:
                                                multiplier = MULTIPLIERS.get(
                                                    suffix.lower(), 1
                                                )
                                                if multiplier:
                                                    number *= multiplier
                                            stock_dict["Market_Cap"] = number
                                        break
                                    mktCap = mktCap.find_next_sibling()
                                if mktCap and mktCap.parent:
                                    blurbline = mktCap.parent.find_next_sibling()
                                    if blurbline:
                                        blurb = str(blurbline.get_text(strip=True))
                                        stock_dict["Blurb"] = remove_weird_chars(blurb)
                                break
                            mktCap = mktCap.find_next_sibling()
                    href = href.replace("r?", "access?")
                    stock_dict["Link"] = href
                    stock_dict["Company"] = link_text
                    subpage_links.append((link_text, href, stock_dict))
    return subpage_links


def extract_company_data(html_content, stock_dict):
    soup = BeautifulSoup(html_content, "html.parser")
    analystTeamNameObj = soup.select_one('input[id="analystTeamName"]')
    if analystTeamNameObj and analystTeamNameObj.has_attr("value"):
        stock_dict["Analyst_Team"] = urllib.parse.unquote(
            analystTeamNameObj.get("value")
        )
    reportSubTitleObj = soup.select_one('input[id="reportSubTitle"]')
    if reportSubTitleObj and reportSubTitleObj.has_attr("value"):
        stock_dict["Report_Subtitle"] = urllib.parse.unquote(
            reportSubTitleObj.get("value")
        )
    keyTakeawaysObj = soup.select_one('ul[class*="key-takeaways-list"]')
    if keyTakeawaysObj:
        key_takeaways = []
        for li in keyTakeawaysObj.find_all("li"):
            text = li.get_text(strip=True)
            if text:
                key_takeaways.append(text)
        if key_takeaways:
            stock_dict["Key_Takeaways"] = key_takeaways
    all_text = []
    ticker_info = soup.select(
        'div[id^="_DataScroller_WAR_RLWebReportsportlet_INSTANCE_"]'
    )
    for ticker in ticker_info:
        ticker_text = ticker.get_text(strip=True)
        if (
            stock_dict["Ticker"].lower() in ticker_text.lower()
            and ticker.find_next_sibling()
            and ("financials" in ticker.find_next_sibling().get_text().lower())
        ):
            data_table = ticker.find_next_sibling()
            if data_table:
                all_text.append(data_table.get_text("|", strip=True))
                divs = data_table.find_all("div")
                relevant_data = []
                for div in divs:
                    direct_texts = [
                        t
                        for t in div.contents
                        if isinstance(t, NavigableString) and t.strip()
                    ]
                    if direct_texts:
                        relevant_data.append(div)
                k = 0
                while k < 3 and data_table:
                    k += 1
                    temp_table = data_table.find_next_sibling()
                    if temp_table and (
                        "EPS" in temp_table.get_text()
                        or "Average Daily Value" in temp_table.get_text()
                    ):
                        data_table = temp_table
                        all_text.append(data_table.get_text("|", strip=True))
                        divs = data_table.find_all("div")
                        for div in divs:
                            direct_texts = [
                                t
                                for t in div.contents
                                if isinstance(t, NavigableString) and t.strip()
                            ]
                            if direct_texts:
                                relevant_data.append(div)
                    elif not temp_table:
                        temp_table = data_table.find_parent()
                        if temp_table and temp_table.find_next_sibling():
                            data_table = temp_table.find_next_sibling()
                            if data_table and (
                                "EPS" in data_table.get_text()
                                or "Average Daily Value" in data_table.get_text()
                            ):
                                all_text.append(data_table.get_text("|", strip=True))
                                divs = data_table.find_all("div")
                                for div in divs:
                                    direct_texts = [
                                        t
                                        for t in div.contents
                                        if isinstance(t, NavigableString) and t.strip()
                                    ]
                                    if direct_texts:
                                        relevant_data.append(div)
                    else:
                        data_table = temp_table
                i = 0
                while i < len(relevant_data):
                    relevant_text = "".join(
                        t.strip()
                        for t in relevant_data[i].contents
                        if isinstance(t, NavigableString)
                    )
                    if "Rating" in relevant_text:
                        i += 1
                        if "Rating" in stock_dict:
                            continue
                        if i >= len(relevant_data):
                            break
                        rating_text = "".join(
                            t.strip()
                            for t in relevant_data[i].contents
                            if isinstance(t, NavigableString)
                        )
                        if "buy" in rating_text.lower():
                            stock_dict["Rating"] = "BUY"
                            i += 1
                        elif "neutral" in rating_text.lower():
                            stock_dict["Rating"] = "NEUTRAL"
                            i += 1
                        elif "underperform" in rating_text.lower():
                            stock_dict["Rating"] = "UNDERPERFORM"
                            i += 1
                        elif "no rating" in rating_text.lower():
                            stock_dict["Rating"] = "NO_RATING"
                            i += 1
                    elif "Price Objective" in relevant_text:
                        i += 1
                        if "Price_Objective" in stock_dict:
                            continue
                        if i >= len(relevant_data):
                            break
                        price_obj_text = "".join(
                            t.strip()
                            for t in relevant_data[i].contents
                            if isinstance(t, NavigableString)
                        )
                        try:
                            price_obj_value = float(price_obj_text.replace(",", ""))
                            stock_dict["Price_Objective"] = price_obj_value
                            i += 1
                            if i >= len(relevant_data):
                                break
                            currency_text = "".join(
                                t.strip()
                                for t in relevant_data[i].contents
                                if isinstance(t, NavigableString)
                            )
                            if currency_text.lower() in CURRENCY_CODES and (
                                not stock_dict.get("Currency")
                            ):
                                stock_dict["Currency"] = currency_text.upper()
                                i += 1
                        except ValueError as error:
                            raise ValueError(
                                "Invalid numeric value in company financials"
                            ) from error
                    elif "Price" in relevant_text:
                        i += 1
                        if "Price" in stock_dict:
                            continue
                        if i >= len(relevant_data):
                            break
                        price_text = "".join(
                            t.strip()
                            for t in relevant_data[i].contents
                            if isinstance(t, NavigableString)
                        )
                        try:
                            price_value = float(price_text.replace(",", ""))
                            stock_dict["Price"] = price_value
                            i += 1
                            if i >= len(relevant_data):
                                break
                            currency_text = "".join(
                                t.strip()
                                for t in relevant_data[i].contents
                                if isinstance(t, NavigableString)
                            )
                            if currency_text.lower() in CURRENCY_CODES:
                                stock_dict["Currency"] = currency_text.upper()
                                i += 1
                        except ValueError as error:
                            raise ValueError(
                                "Invalid numeric value in company financials"
                            ) from error
                    elif "Upside" in relevant_text:
                        i += 1
                        if "Upside" in stock_dict:
                            continue
                        if i >= len(relevant_data):
                            break
                        upside_text = "".join(
                            t.strip()
                            for t in relevant_data[i].contents
                            if isinstance(t, NavigableString)
                        )
                        try:
                            upside_value = (
                                float(upside_text.strip("%").replace(",", "")) / 100
                            )
                            stock_dict["Upside"] = upside_value
                            i += 1
                        except ValueError as error:
                            raise ValueError(
                                "Invalid numeric value in company financials"
                            ) from error
                    elif "Market Cap" in relevant_text:
                        i += 1
                        if "Market_Cap" in stock_dict:
                            continue
                        if i >= len(relevant_data):
                            break
                        mkt_cap_text = "".join(
                            t.strip()
                            for t in relevant_data[i].contents
                            if isinstance(t, NavigableString)
                        )
                        try:
                            mkt_cap_value = float(mkt_cap_text.replace(",", ""))
                            i += 1
                            if i >= len(relevant_data):
                                break
                            currency_factor_text = "".join(
                                t.strip()
                                for t in relevant_data[i].contents
                                if isinstance(t, NavigableString)
                            )
                            cap_match = re.match(
                                "([A-Z]+)\\(([^)]+)\\)", currency_factor_text
                            )
                            if cap_match:
                                currency, multiplier = cap_match.groups()
                                if multiplier.lower() in MULTIPLIERS:
                                    mkt_cap_value *= MULTIPLIERS[multiplier.lower()]
                                if currency.lower() in CURRENCY_CODES and (
                                    not stock_dict.get("Currency")
                                ):
                                    stock_dict["Currency"] = currency.upper()
                                i += 1
                            stock_dict["Market_Cap"] = mkt_cap_value
                        except ValueError as error:
                            raise ValueError(
                                "Invalid numeric value in company financials"
                            ) from error
                    elif "Average Daily Value" in relevant_text:
                        i += 1
                        if "Average_Daily_Value" in stock_dict:
                            continue
                        if i >= len(relevant_data):
                            break
                        adv_text = "".join(
                            t.strip()
                            for t in relevant_data[i].contents
                            if isinstance(t, NavigableString)
                        )
                        try:
                            adv_value = float(adv_text.replace(",", ""))
                            i += 1
                            if i >= len(relevant_data):
                                break
                            currency_factor_text = "".join(
                                t.strip()
                                for t in relevant_data[i].contents
                                if isinstance(t, NavigableString)
                            )
                            cap_match = re.match(
                                "([A-Z]+)\\(([^)]+)\\)", currency_factor_text
                            )
                            if cap_match:
                                currency, multiplier = cap_match.groups()
                                if multiplier.lower() in MULTIPLIERS:
                                    adv_value *= MULTIPLIERS[multiplier.lower()]
                                if currency.lower() in CURRENCY_CODES and (
                                    not stock_dict.get("Currency")
                                ):
                                    stock_dict["Currency"] = currency.upper()
                                i += 1
                            stock_dict["Average_Daily_Value"] = adv_value
                        except ValueError as error:
                            raise ValueError(
                                "Invalid numeric value in company financials"
                            ) from error
                    elif (
                        "EPS" in relevant_text
                        and sanitize_filename(relevant_text) not in stock_dict
                    ):
                        i += 1
                        if i >= len(relevant_data):
                            break
                        eps_text = "".join(
                            t.strip()
                            for t in relevant_data[i].contents
                            if isinstance(t, NavigableString)
                        )
                        try:
                            eps_value = float(eps_text.replace(",", ""))
                            stock_dict[sanitize_filename(relevant_text)] = eps_value
                            i += 1
                            if i >= len(relevant_data):
                                break
                            currency_text = "".join(
                                t.strip()
                                for t in relevant_data[i].contents
                                if isinstance(t, NavigableString)
                            )
                            if currency_text.lower() in CURRENCY_CODES and (
                                not stock_dict.get("Currency")
                            ):
                                stock_dict["Currency"] = currency_text.upper()
                                i += 1
                        except ValueError as error:
                            raise ValueError(
                                "Invalid numeric value in company financials"
                            ) from error
                    else:
                        i += 1
                for i in range(len(all_text)):
                    all_text[i] = " ".join(all_text[i].split())
                stock_dict["Raw_Text"] = all_text
                break
    if not stock_dict.get("Raw_Text"):
        raise ValueError(
            "Company page has no matching financials; it may be unavailable or require login"
        )
    return stock_dict


def remove_weird_chars(s):
    allowed = set(string.ascii_letters + string.digits + string.punctuation + " ")
    return "".join(c for c in s if c in allowed)
