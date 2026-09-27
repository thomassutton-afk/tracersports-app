"""
Season-independent reference data.

Team names and campus locations barely change year to year, so this gets built
once and just keeps paying off on every future season. When a new season turns
up a name variant or opponent we haven't seen, add it here (or call
add_alias/add_home_city) rather than special-casing it in that season's parser.
"""
import re

# alias (as seen in some source) -> canonical name (as used in teams.team_name)
FCS_ALIASES = {
    'Austin Peay State': 'Austin Peay', 'Austin Peay St.': 'Austin Peay',
    'Austin Peay St. (TN)': 'Austin Peay',
    'Southeast Missouri State': 'SE Missouri State', 'Southeast Missouri St.': 'SE Missouri State',
    'Troy State': 'Troy',
    'Central Connecticut State': 'Central Connecticut', 'Central Connecticut St.': 'Central Connecticut',
    'Saint Francis': 'Saint Francis (PA)',
    'Towson State': 'Towson',
    'Southwest Missouri State': 'Missouri State', 'Missouri St.': 'Missouri State',
    'Southwest Texas State': 'Texas State', 'Texas St.': 'Texas State',
    'Bethune-Cookman': 'Bethune-Cookman',
    'UT Martin': 'Tennessee-Martin', 'Tennessee-Martin': 'Tennessee-Martin',
    'Middle Tennessee St.': 'Middle Tennessee',
    'Tennessee St.': 'Tennessee State', 'Illinois St.': 'Illinois State',
    'Murray St.': 'Murray State', 'Murray St. (KY)': 'Murray State',
    'Western Kentucky St.': 'Western Kentucky',
    'Morehead St.': 'Morehead State', 'Morehead St. (KY)': 'Morehead State',
    'Youngstown St.': 'Youngstown State', 'Youngstown St. (OH)': 'Youngstown State',
    'Charleston Southern (SC)': 'Charleston Southern',
    'Southern Utah St.': 'Southern Utah',
    'Cal Poly-San Luis Obispo': 'Cal Poly',
    "Saint Mary's (CA)": "Saint Mary's",
    'Boston (MA)': 'Boston University',  # ambiguous - verify per-season if this stops being a Yankee-conf context
    'Appalachian St.': 'Appalachian State',
    'Citadel': 'The Citadel',
    "Saint John's": "St. John's",
}

# team_name (as used in teams.team_name) -> home city, "City, ST"
FCS_HOME_CITY = {
    'Montana': 'Missoula, MT', 'Northern Arizona': 'Flagstaff, AZ',
    'Cal State Northridge': 'Northridge, CA', 'Weber State': 'Ogden, UT',
    'Eastern Washington': 'Cheney, WA', 'Montana State': 'Bozeman, MT',
    'Idaho State': 'Pocatello, ID', 'Sacramento State': 'Sacramento, CA',
    'Portland State': 'Portland, OR',
    'Northern Iowa': 'Cedar Falls, IA', 'Western Illinois': 'Macomb, IL',
    'Missouri State': 'Springfield, MO', 'Indiana State': 'Terre Haute, IN',
    'Southern Illinois': 'Carbondale, IL', 'Illinois State': 'Normal, IL',
    'Dartmouth': 'Hanover, NH', 'Columbia': 'New York, NY', 'Brown': 'Providence, RI',
    'Cornell': 'Ithaca, NY', 'Penn': 'Philadelphia, PA', 'Harvard': 'Cambridge, MA',
    'Princeton': 'Princeton, NJ', 'Yale': 'New Haven, CT',
    'Duquesne': 'Pittsburgh, PA', 'Georgetown': 'Washington, DC',
    'Marist': 'Poughkeepsie, NY', "St. John's": 'Queens, NY',
    'Canisius': 'Buffalo, NY', "Saint Peter's": 'Jersey City, NJ',
    'Siena': 'Loudonville, NY', 'Fairfield': 'Fairfield, CT', 'Iona': 'New Rochelle, NY',
    'Florida A&M': 'Tallahassee, FL', 'Howard': 'Washington, DC',
    'North Carolina A&T': 'Greensboro, NC', 'South Carolina State': 'Orangeburg, SC',
    'Hampton': 'Hampton, VA', 'Morgan State': 'Baltimore, MD',
    'Delaware State': 'Dover, DE', 'Bethune-Cookman': 'Daytona Beach, FL',
    'Robert Morris': 'Moon Township, PA', 'Monmouth': 'West Long Branch, NJ',
    'Central Connecticut': 'New Britain, CT', 'Wagner': 'Staten Island, NY',
    'Saint Francis (PA)': 'Loretto, PA',
    'Murray State': 'Murray, KY', 'Eastern Illinois': 'Charleston, IL',
    'Eastern Kentucky': 'Richmond, KY', 'Middle Tennessee': 'Murfreesboro, TN',
    'Tennessee Tech': 'Cookeville, TN', 'Tennessee State': 'Nashville, TN',
    'SE Missouri State': 'Cape Girardeau, MO', 'Austin Peay': 'Clarksville, TN',
    'Tennessee-Martin': 'Martin, TN',
    'Bucknell': 'Lewisburg, PA', 'Colgate': 'Hamilton, NY', 'Lehigh': 'Bethlehem, PA',
    'Lafayette': 'Easton, PA', 'Fordham': 'Bronx, NY', 'Holy Cross': 'Worcester, MA',
    'Dayton': 'Dayton, OH', 'Drake': 'Des Moines, IA', 'Evansville': 'Evansville, IN',
    'Butler': 'Indianapolis, IN', 'San Diego': 'San Diego, CA', 'Valparaiso': 'Valparaiso, IN',
    'Marshall': 'Huntington, WV', 'East Tennessee State': 'Johnson City, TN',
    'Furman': 'Greenville, SC', 'Appalachian State': 'Boone, NC',
    'The Citadel': 'Charleston, SC', 'Georgia Southern': 'Statesboro, GA',
    'VMI': 'Lexington, VA', 'Chattanooga': 'Chattanooga, TN',
    'Western Carolina': 'Cullowhee, NC',
    'Troy': 'Troy, AL', 'Nicholls State': 'Thibodaux, LA',
    'Stephen F. Austin': 'Nacogdoches, TX', 'Northwestern State': 'Natchitoches, LA',
    'Sam Houston State': 'Huntsville, TX', 'Texas State': 'San Marcos, TX',
    'McNeese State': 'Lake Charles, LA',
    'Jackson State': 'Jackson, MS', 'Southern': 'Baton Rouge, LA',
    'Mississippi Valley State': 'Itta Bena, MS', 'Texas Southern': 'Houston, TX',
    'Alcorn State': 'Lorman, MS', 'Grambling State': 'Grambling, LA',
    'Alabama State': 'Montgomery, AL', 'Prairie View A&M': 'Prairie View, TX',
    'New Hampshire': 'Durham, NH', 'Maine': 'Orono, ME', 'UMass': 'Amherst, MA',
    'Connecticut': 'Storrs, CT', 'Rhode Island': 'Kingston, RI',
    'Boston University': 'Boston, MA', 'William & Mary': 'Williamsburg, VA',
    'Villanova': 'Villanova, PA', 'Delaware': 'Newark, DE',
    'James Madison': 'Harrisonburg, VA', 'Northeastern': 'Boston, MA',
    'Richmond': 'Richmond, VA',
    'Buffalo': 'Buffalo, NY', 'Youngstown State': 'Youngstown, OH',
    "Saint Mary's": 'Moraga, CA', 'Western Kentucky': 'Bowling Green, KY',
    'Davidson': 'Davidson, NC', 'Towson': 'Towson, MD', 'Samford': 'Birmingham, AL',
    'Wofford': 'Spartanburg, SC', 'Cal Poly': 'San Luis Obispo, CA',
    'Hofstra': 'Hempstead, NY', 'Liberty': 'Lynchburg, VA',
    'Southern Utah': 'Cedar City, UT', 'Charleston Southern': 'Charleston, SC',
    'Morehead State': 'Morehead, KY', 'Jacksonville State': 'Jacksonville, AL',
}


def norm(s):
    return s.replace('\u2013', '-').replace('\u2019', "'").strip()


def strip_state_suffix(name):
    return re.sub(r'\s*\([A-Za-z]{2,3}\)\s*$', '', name).strip()


def seed_reference_tables(con):
    cur = con.cursor()
    cur.executemany("INSERT OR REPLACE INTO team_aliases VALUES (?,?)", FCS_ALIASES.items())
    cur.executemany("INSERT OR REPLACE INTO team_home_city VALUES (?,?)", FCS_HOME_CITY.items())
    con.commit()


def add_alias(con, alias, canonical_name):
    con.execute("INSERT OR REPLACE INTO team_aliases VALUES (?,?)", (alias, canonical_name))
    con.commit()


def add_home_city(con, team_name, city):
    con.execute("INSERT OR REPLACE INTO team_home_city VALUES (?,?)", (team_name, city))
    con.commit()


def resolve_fcs_name(con, name, season):
    """Resolve any name variant to the canonical team_name for this season, or None
    if it isn't an FCS team that season. Tries: exact match against this season's
    team list -> team_aliases table -> state-suffix-stripped versions of both."""
    cur = con.cursor()
    season_names = {norm(r[0]): r[0] for r in cur.execute(
        "SELECT team_name FROM teams WHERE season=?", (season,))}
    for candidate in (name, strip_state_suffix(name)):
        n = norm(candidate)
        if n in season_names:
            return season_names[n]
        row = cur.execute("SELECT canonical_name FROM team_aliases WHERE alias=?", (candidate,)).fetchone()
        if row:
            # canonical name still has to exist for this season
            canon = row[0]
            if norm(canon) in season_names:
                return season_names[norm(canon)]
            return canon  # trust the alias even if this season's team list lookup is incomplete
    return None


def classify_location(con, team, opponent_fcs, location_text):
    """home/away/neutral/unresolved from `team`'s perspective, using team_home_city."""
    cur = con.cursor()
    team_city = cur.execute("SELECT city FROM team_home_city WHERE team_name=?", (team,)).fetchone()
    opp_city = None
    if opponent_fcs:
        row = cur.execute("SELECT city FROM team_home_city WHERE team_name=?", (opponent_fcs,)).fetchone()
        opp_city = row[0] if row else None
    team_city = team_city[0] if team_city else None
    if not location_text:
        return 'unresolved'
    loc_n = norm(location_text)
    if team_city and norm(team_city) == loc_n:
        return 'home'
    if opp_city and norm(opp_city) == loc_n:
        return 'away'
    return 'neutral'
