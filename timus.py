import time
import datetime
import urllib2
import urlparse
import re
from BeautifulSoup import BeautifulSoup

## Configuration
START = '09:00:00 25 Sep 2009'
END = '12:00:00 25 Sep 2009'
USERS = {
    80862: 'Orfest',
    71690: 'ahmedov',
}
PROBLEMS = {
    1102: 'A', 1027: 'B', 1502: 'C', 1001: 'D', 1306: 'E'
}
WRONG_PENALTY = 20
CRAWL_PAUSE = 5.0 # Pause between requests


class odict(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError


def parse_date(str):
    """Parse date from given, e.g. ``09:53:38 25 Sep 2009``."""
    if isinstance(str, datetime.datetime):
        return str
    return datetime.datetime.strptime(str, '%H:%M:%S %d %b %Y')


def extract(soup):
    footer = soup.find('td', {'class': 'footer_right'})
    next_link = footer.find('a', text=re.compile('Next')).parent['href']
    table = soup.find('table', {'class': 'status'})
    items = []
    def user_url_to_id(url):
        """author.aspx?id=84033 => 84033"""
        return int(url[url.find('id=')+3:])
    column_extractors = {
        'id': ('id', lambda col: col.string.strip()),
        'date': ('date', lambda col: parse_date(u' '.join(
                            map(unicode.strip, col.findAll(text=True))))),
        'verdict_ac': ('status', lambda col: col.string.strip()),
        'verdict_rj': ('status', lambda col: col.string.strip()),
        'problem': ('problem', lambda col: int(col.find('a').string.strip())),
        # We want an ID only
        'coder': ('user', lambda col: (user_url_to_id(col.find('a')['href'])))
    }
    for row in table.findAll('tr'):
        if row['class'] in ('header',):
            continue
        data = odict()
        for col in row.findAll('td'):
            css = col['class']
            if css in column_extractors:
                key, fn = column_extractors[css]
                data[key] = fn(col)
        items.append(data)
    return next_link, items

def minutes(delta):
    assert delta.days == 0
    return delta.seconds / 60

def print_board(board, start_date):
    table = dict()
    scores = dict()
    # Calculate the score by assigning penalties etc.
    for user in USERS:
        scores[user] = odict(solved=0, minutes=0)
        for problem in PROBLEMS:
            table.setdefault(user, {})[problem] = odict(plus='', time='')
            status = board[user][problem]
            if status.accepted:
                delta = minutes(status.accepted - start_date)
                table[user][problem].update(
                    plus='+%s' % (str(status.wrong) if status.wrong else ''),
                    time='%d:%.2d' % divmod(delta, 60))
                scores[user].solved += 1
                scores[user].minutes += delta + WRONG_PENALTY * status.wrong
            elif status.wrong:
                table[user][board].plus = '-%d' % status.wrong
    # Generate the table
    problems_sorted = sorted(PROBLEMS.keys(), key=PROBLEMS.get)
    def compare(a, b):
        return -cmp(scores[a].solved, scores[b].solved) or \
               cmp(scores[a].minutes, scores[b].minutes)
    for problem in problems_sorted:
        print '| %s (%d)' % (PROBLEMS[problem], problem),
    print
    for user in sorted(USERS, cmp=compare):
        print USERS[user], scores[user].minutes,
        for problem in problems_sorted:
            print '| %s %s' % (table[user][problem].plus,
                               table[user][problem].time),
        print

def main(start_url='http://acm.timus.ru/status.aspx?count=100'):
    start_date, end_date = parse_date(START), parse_date(END)
    seen = set() # set of seen submission IDs
    board = dict()
    for user in USERS:
        for problem in PROBLEMS:
            board.setdefault(user, {})[problem] = odict(accepted=False, wrong=0)

    url = start_url
    seen_older = seen_newer = False
    while not seen_older:
        print 'Retrieving %s...' % url
        soup = BeautifulSoup(urllib2.urlopen(url))
        next_link, items = extract(soup)
        url = urlparse.urljoin(url, next_link)
        for item in items:
            if item.date > end_date:
                seen_newer = True
            if item.date < start_date:
                seen_older = True
            if item.id not in seen and \
               item.problem in PROBLEMS and item.user in USERS and \
               start_date <= item.date <= end_date:
               # Was the problem already accepted for this team?
               if board[item.user][item.problem].accepted and \
                  item.date > board[item.user][item.problem].accepted:
                   # Different time might mean higher (= worse) time
                   continue
               # Accepted?
               if item.status in ('Accepted',):
                   board[item.user][item.problem].accepted = item.date
               else:
                   board[item.user][item.problem].wrong += 1
               seen.add(id)
        if not seen_older:
            time.sleep(CRAWL_PAUSE)

    print_board(board, start_date)


if __name__ == '__main__':
    main()
