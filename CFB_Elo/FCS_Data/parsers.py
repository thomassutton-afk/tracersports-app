"""
Parsers for the source formats we've actually seen. If next season's files come
from the same places (Wikipedia-style exports, the record-book style archive,
screenshots), these should work with little or no change.
"""
import re

MONTHS = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
          'September', 'October', 'November', 'December')


# ---------------------------------------------------------------------------
# Format 1: the messy multi-team "Wikipedia schedule table" export
# (e.g. FCS_Schedules_1996.txt). One "Team: <name>" block per team, a header
# row naming the columns, then each game usually split across 2-3 physical
# lines because the Site cell had an embedded newline in the source table.
# ---------------------------------------------------------------------------

def _is_date_line(line):
    return line.split('\t')[0].strip().startswith(MONTHS)


def parse_wikipedia_schedule(raw_text):
    """Returns {full_team_name: [game_dict, ...]}. game_dict has raw fields;
    caller is responsible for resolving opponent names and computing wl/scores
    via clean_opponent()/parse_result() below."""
    raw = raw_text.replace('\r\n', '\n')
    blocks = re.split(r'(?=^Team: )', raw, flags=re.M)
    result = {}
    for block in blocks:
        if not block.startswith('Team: '):
            continue
        lines = block.split('\n')
        team_name = lines[0][len('Team: '):].strip()
        header_idx = next((i for i, l in enumerate(lines) if l.startswith('Date\t')), None)
        if header_idx is None:
            result[team_name] = []
            continue
        header_cols = lines[header_idx].split('\t')
        site_idx = header_cols.index('Site')
        pre_cols = header_cols[:site_idx]
        post_cols = header_cols[site_idx + 1:]

        games = []
        i = header_idx + 1
        n = len(lines)
        while i < n:
            line = lines[i]
            if not line.strip() or not _is_date_line(line):
                i += 1
                continue
            f1 = line.split('\t')
            site_val_on_line1 = f1[site_idx].strip() if len(f1) > site_idx else ''
            if site_val_on_line1:
                rec = {col: val.strip() for col, val in zip(pre_cols, f1)}
                rec['Site'] = site_val_on_line1
                f3 = [x.strip() for x in f1[site_idx + 1:]]
                i += 1
            else:
                if i + 2 >= n:
                    break
                l2, l3 = lines[i + 1], lines[i + 2]
                rec = {col: val.strip() for col, val in zip(pre_cols, f1)}
                rec['Site'] = l2.strip()
                f3 = [x.strip() for x in l3.split('\t')]
                i += 3

            result_idx = next((idx for idx, val in enumerate(f3)
                                if re.match(r'^[WLT]\s+\d+\s*[\u2013\-]\s*\d+', val)), None)
            if result_idx is None:
                for col, val in zip(post_cols, f3):
                    rec[col] = val
            else:
                if 'TV' in post_cols:
                    rec['TV'] = ' '.join(f3[:result_idx]) if result_idx > 0 else ''
                rec['Result'] = f3[result_idx]
                rest = f3[result_idx + 1:]
                trailing_cols = [c for c in post_cols if c not in ('TV', 'Result')]
                for col, val in zip(trailing_cols, rest):
                    rec[col] = val
            games.append(rec)
        result[team_name] = games
    return result


def clean_opponent(raw_opp):
    """Returns (opponent_clean, location, opp_rank, non_conf, homecoming)."""
    s = raw_opp
    location = 'home'
    if s.startswith('at '):
        location = 'away'
        s = s[3:]
    elif s.startswith('vs. ') or s.startswith('vs.'):
        location = 'neutral'
        s = s.split('vs.', 1)[1].strip()
    non_conf = '*' in s
    s = s.replace('*', '').replace('^', '')
    homecoming = 'dagger' in s
    s = s.replace('dagger', '')
    opp_rank = None
    m = re.match(r'^No\.\s*(?:T[\u2013\-])?(\d+)\s+(.*)$', s.strip())
    if m:
        opp_rank = int(m.group(1))
        s = m.group(2)
    return s.strip(), location, opp_rank, non_conf, homecoming


def parse_result(res):
    if not res:
        return None, None, None, None
    m = re.match(r'^([WLT])\s+(\d+)[\u2013\-](\d+)(?:\s+(\S+))?', res)
    if not m:
        return None, None, None, None
    wl, s1, s2, ot = m.groups()
    return wl, int(s1), int(s2), ot


# ---------------------------------------------------------------------------
# Format 2: the "record book" style export, one page per team with a
# Coach line, a W/L-Date-PF-Opponent-PA-Location-Notes table, and a
# "Season Totals" footer (e.g. FCS_LostSchedules_1996.txt).
# ---------------------------------------------------------------------------

def parse_recordbook_schedules(raw_text):
    """Returns {team_name: {'record': 'W-L-T', 'wins':.., 'losses':.., 'ties':..,
    'games': [{'wl','date','pf','opponent_raw','pa','location','notes'}, ...]}}"""
    pattern = re.compile(r'\n([A-Za-z][^\n]*?):\s*\n(\d{4}):\s*([\d]+)-([\d]+)-([\d]+)')
    matches = list(pattern.finditer(raw_text))
    result = {}
    for i, m in enumerate(matches):
        name = m.group(1).strip()
        w, l, t = int(m.group(3)), int(m.group(4)), int(m.group(5))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
        block = raw_text[start:end]
        games = _parse_recordbook_games(block)
        result[name] = {'record': f'{w}-{l}-{t}', 'wins': w, 'losses': l, 'ties': t, 'games': games}
    return result


def _parse_recordbook_games(block_text):
    idx_totals = block_text.find('Season Totals')
    section = block_text[:idx_totals] if idx_totals != -1 else block_text
    lines = [l.strip() for l in section.split('\n') if l.strip()]
    try:
        header_end = max(i for i, l in enumerate(lines) if l == 'Notes')
    except ValueError:
        header_end = -1
    game_lines = lines[header_end + 1:]

    games = []
    pos, n = 0, len(game_lines)
    while pos < n:
        if game_lines[pos] not in ('W', 'L', 'T'):
            pos += 1
            continue
        if pos + 5 >= n:
            break
        wl, date, pf, opp, pa, loc = game_lines[pos:pos + 6]
        pos += 6
        notes = ''
        if pos < n and game_lines[pos] not in ('W', 'L', 'T'):
            notes = game_lines[pos]
            pos += 1
        games.append({'wl': wl, 'date': date, 'pf': int(pf), 'opponent_raw': opp,
                       'pa': int(pa), 'location': loc, 'notes': notes})
    return games
