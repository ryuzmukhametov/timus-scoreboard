"""Scoreboard for the Timus contest system (http://acm.timus.ru/).

Since Timus does not allow the creation of custom contests, this script
helps by scraping the judge status pages in order to generate score
table (all according to ACM rules).
"""

import time
import datetime
import urllib2
import urlparse
import re
import ConfigParser

from BeautifulSoup import BeautifulSoup
import jinja2


def parse_date(str):
    """Parse date from given, e.g. ``09:53:38 25 Sep 2009``.
    
    While this is not the most usual format, it is used by the Timus system
    and therefore I took the opportunity to reuse it widely."""
    if isinstance(str, datetime.datetime):
        return str
    return datetime.datetime.strptime(str, '%H:%M:%S %d %b %Y')


def get_minutes(delta):
    """Extract the number of minutes from timedelta object."""
    return delta.days * 24 * 60 + delta.seconds / 60


class odict(dict):
    """Dictionary that allows attribute access, e.g. if `foo` is instance
    of `odict` then foo.x == foo['x']."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError


class Contest(object):
    """Contest configuration."""

    def __init__(self):
        if self.title is None or \
           self.start is None or \
           self.end is None or \
           not self.users or \
           not self.problems:
            raise ValueError("Incomplete configuration")

    # Name of the contest
    title = None

    # Contest start and end date, either an instance of datetime,
    # or something like `09:00:00 25 Sep 2009`
    start = None
    end = None

    # Mapping: user ID => display name
    users = dict()

    # Mapping: problem ID => task name (A/B/C... is typical for ACM)
    problems = dict()

    # Self-explanatory configuration variables
    wrong_penalty = 20
    crawl_pause = 5.0
    update_interval = 60.0


class ConfiguredContest(Contest):
    """Subclass of Contest that reads configuration from a text file.
    """

    def __init__(self, fp):
        parser = ConfigParser.ConfigParser()
        parser.readfp(fp)
        self.load_configuration(parser)
        super(ConfiguredContest, self).__init__()

    def load_configuration(self, parser):
        self.title = parser.get('contest', 'title')
        self.start = parse_date(parser.get('contest', 'start'))
        self.end = parse_date(parser.get('contest', 'end'))
        self.users = dict(parser.items('users'))
        self.problems = dict(parser.items('problems'))
        for name, getter in (('wrong_penalty', 'getint'),
                             ('crawl_pause', 'getfloat'),
                             ('update_interval', 'getfloat')):
            if parser.has_option('config', name):
                value = getattr(parser, getter)('config', name)
                setattr(self, name, value)


def extract(soup):
    footer = soup.find('td', {'class': 'footer_right'})
    next_link = footer.find('a', text=re.compile('Next')).parent['href']
    table = soup.find('table', {'class': 'status'})
    items = []
    def user_url_to_id(url):
        """author.aspx?id=84033 => 84033"""
        return int(url[url.find('id=')+3:])
    def all_child_text(col):
        return u' '.join(map(unicode.strip, col.findAll(text=True)))
    column_extractors = {
        'id': ('id', lambda col: all_child_text(col)),
        'date': ('date', lambda col: parse_date(all_child_text(col))),
        'verdict_ac': ('status', lambda col: all_child_text(col)),
        'verdict_rj': ('status', lambda col: all_child_text(col)),
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


def get_render_context(board, start_date):
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
                table[user][problem].plus = '-%d' % status.wrong
    # Generate the table
    def compare(a, b):
        return -cmp(scores[a].solved, scores[b].solved) or \
               cmp(scores[a].minutes, scores[b].minutes) or \
               cmp(USERS[a], USERS[b])
    return {
        'title': TITLE,
        'users_sorted': sorted(USERS, cmp=compare),
        'problems_sorted': sorted(PROBLEMS, key=PROBLEMS.get),
        'users': USERS,
        'problems': PROBLEMS,
        'scores': scores,
        'table': table
    }


def main(start_url='http://acm.timus.ru/status.aspx?count=100'):
    start_date, end_date = parse_date(START), parse_date(END)
    env = jinja2.Environment(loader=jinja2.FileSystemLoader('templates'))

    seen = set() # set of seen submission IDs
    board = dict()
    for user in USERS:
        for problem in PROBLEMS:
            board.setdefault(user, {})[problem] = odict(accepted=False, wrong=0)

    def update():
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
        return not seen_newer

    def output():
        context = get_render_context(board, start_date)
        for template in ('index.html', 'top.html', 'table.html'):
            output_name = 'output/%s' % template
            print 'Writing %s...' % output_name
            with open(output_name, 'w') as fp:
                template = env.get_template(template)
                print >>fp, template.render(context).encode('utf-8')

    while True:
        contest_in_progress = update()
        output()
        if not contest_in_progress:
            print 'Contest has ended.'
            break
        time.sleep(UPDATE_INTERVAL)

if __name__ == '__main__':
    main()
