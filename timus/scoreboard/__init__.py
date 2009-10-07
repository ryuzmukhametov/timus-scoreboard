"""Scoreboard for the Timus contest system (http://acm.timus.ru/).

Since Timus does not allow the creation of custom contests, this script
helps by scraping the judge status pages in order to generate score
table (all according to ACM rules).
"""

from __future__ import with_statement

import sys
import os.path
import time
import datetime
import urllib2
import urlparse
import re
import optparse

import jinja2
from BeautifulSoup import BeautifulSoup
from configobj import ConfigObj


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
        if self.title is None or self.start is None or \
           self.end is None or not self.users or not self.problems:
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
    start_url = 'http://acm.timus.ru/status.aspx?count=100'
    template_dir = None
    templates = ('index.html', 'top.html', 'table.html')
    output_dir = 'output'


class ConfiguredContest(Contest):
    """Subclass of Contest that reads configuration from a text file.
    """

    def __init__(self, source):
        config = ConfigObj(source, list_values=False, file_error=True,
                           encoding='utf-8')
        self.load_configuration(config)
        super(ConfiguredContest, self).__init__()

    def load_configuration(self, config):
        self.title = config['contest']['title']
        self.start = parse_date(config['contest']['start'])
        self.end = parse_date(config['contest']['end'])
        self.users = dict(config['users'].dict())
        self.problems = dict(config['problems'].dict())
        if 'config' in config:
            section = config['config']
            for name, getter in (('wrong_penalty', 'as_int'),
                                 ('crawl_pause', 'as_float'),
                                 ('update_interval', 'as_float'),
                                 ('start_url', '__getitem__'),
                                 ('template_dir', '__getitem__'),
                                 ('output_dir', '__getitem__')):
                if name in section:
                    value = getattr(section, getter)(name)
                    setattr(self, name, value)
            # Special handling. Or we could just use list parsing from
            # configobj.
            if 'templates' in section:
                self.templates = section['templates'].split()


class Crawler(object):
    """Timus crawler and submission aggregator."""

    def __init__(self, contest):
        self.contest = contest
        # Set of seen submission IDs
        self.seen = set()
        # Build an empty board
        self.board = dict()
        for user in self.contest.users:
            self.board[user] = dict()
            for problem in self.contest.problems:
                self.board[user][problem] = odict(accepted=False, wrong=0)

    def run(self, once=False):
        env = jinja2.Environment(loader=self.build_template_loader())
        while True:
            contest_in_progress = self.update()
            self.output(env)
            if once:
                break
            if not contest_in_progress:
                self.log('Contest has ended.')
                break
            time.sleep(self.contest.update_interval)

    def log(self, message):
        """Log a message."""
        # TODO: use logging module from stdlib or at least print the date
        sys.stderr.write(message)
        sys.stderr.write('\n')

    def build_template_loader(self):
        """Build Jinja2 template loader that allows users to override templates
        yet falls back to the ones shipped with this package."""
        loaders = [jinja2.PackageLoader(__name__, 'templates')]
        if self.contest.template_dir is not None:
            loaders.insert(0, jinja2.FileSystemLoader(template_dir))
        return jinja2.ChoiceLoader(loaders)

    def extract(self, source):
        """Extract items and link to the next page from the judge status page."""
        soup = BeautifulSoup(source)
        footer = soup.find('td', {'class': 'footer_right'})
        next_link = footer.find('a', text=re.compile('Next')).parent['href']
        table = soup.find('table', {'class': 'status'})
        items = []
        def user_url_to_id(url):
            """author.aspx?id=84033 => 84033"""
            return url[url.find('id=')+3:]
        def all_child_text(col):
            return u' '.join(map(unicode.strip, col.findAll(text=True)))
        column_extractors = {
            'id': ('id', lambda col: all_child_text(col)),
            'date': ('date', lambda col: parse_date(all_child_text(col))),
            'verdict_ac': ('status', lambda col: all_child_text(col)),
            'verdict_rj': ('status', lambda col: all_child_text(col)),
            'problem': ('problem', lambda col: col.find('a').string.strip()),
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

    def build_render_context(self):
        """Build context for the templates."""
        table = dict()
        scores = dict()
        # Calculate the score by assigning penalties etc.
        for user in self.contest.users:
            scores[user] = odict(solved=0, minutes=0)
            for problem in self.contest.problems:
                table.setdefault(user, {})[problem] = odict(plus='', time='')
                status = self.board[user][problem]
                if status.accepted:
                    delta = get_minutes(status.accepted - self.contest.start)
                    table[user][problem].update(
                        plus='+%s' % (str(status.wrong) if status.wrong else ''),
                        time='%d:%.2d' % divmod(delta, 60))
                    scores[user].solved += 1
                    scores[user].minutes += delta
                    scores[user].minutes += self.contest.wrong_penalty * status.wrong
                elif status.wrong:
                    table[user][problem].plus = '-%d' % status.wrong
        def compare_users(a, b):
            """User comparator that sorts by problems solved first, next by minutes,
            then by the display name."""
            return -cmp(scores[a].solved, scores[b].solved) or \
                   cmp(scores[a].minutes, scores[b].minutes) or \
                   cmp(self.contest.users[a], self.contest.users[b])
        return {
            'date': datetime.datetime.utcnow(),
            'title': self.contest.title,
            'users': self.contest.users,
            'users_sorted': sorted(self.contest.users, cmp=compare_users),
            # Sort by name
            'problems': self.contest.problems,
            'problems_sorted': sorted(self.contest.problems,
                                      key=self.contest.problems.get),
            'scores': scores,
            'table': table
        }

    def update(self):
        """Crawl the pages and update the board."""
        url = self.contest.start_url
        seen_older = seen_newer = seen_seen = False
        while not seen_older and not seen_seen:
            self.log('Retrieving %s...' % url)
            source = urllib2.urlopen(url)
            next_link, items = self.extract(source)
            url = urlparse.urljoin(url, next_link)
            ## TODO: we should not recrawl all pages every time. An easy fix
            ## would be to stop fetching new pages as soon as there are 
            ## `seen` items already.
            for item in items:
                if item.date > self.contest.end:
                    seen_newer = True
                if item.date < self.contest.start:
                    seen_older = True
                if item.id in self.seen:
                    seen_seen = True
                    continue
                if item.problem in self.contest.problems and \
                   item.user in self.contest.users and \
                   self.contest.start <= item.date <= self.contest.end:
                   # Was the problem already accepted for this team?
                   if self.board[item.user][item.problem].accepted and \
                      item.date > self.board[item.user][item.problem].accepted:
                       # Different time might mean higher (= worse) time
                       continue
                   # Accepted?
                   if item.status in ('Accepted',):
                       self.board[item.user][item.problem].accepted = item.date
                   else:
                       self.board[item.user][item.problem].wrong += 1
                   self.seen.add(item.id)
            if not seen_older:
                time.sleep(self.contest.crawl_pause)
        return not seen_newer

    def output(self, env):
        """Output the board and other pages based on the templates."""
        context = self.build_render_context()
        for template in self.contest.templates:
            output_name = os.path.join(self.contest.output_dir, template)
            self.log('Writing %s...' % output_name)
            with open(output_name, 'w') as fp:
                template = env.get_template(template)
                print >>fp, template.render(context).encode('utf-8')


def main():
    usage = "usage: %prog [options] configuration-file"
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('-n', '--once', dest='once', action='store_true',
                      help="Quit immediately after updating the board")
    (options, args) = parser.parse_args()
    if len(args) != 1:
        parser.error("name of the configuration file must be given")
    with open(args[0]) as fp:
        contest = ConfiguredContest(fp)
        crawler = Crawler(contest)
        crawler.run(once=options.once)


if __name__ == '__main__':
    main()
