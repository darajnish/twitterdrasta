'''
MIT License

Copyright (c) 2020 Rajnish Mishra

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

This program helps in forwarding tweets from a public twitter handle to a telegram
channel.
@package TwitterDrasta
'''

import tweepy
import logging
import json
import signal
import psycopg2 as pg
from time import sleep
from argparse import ArgumentParser
from telegram.ext import Updater, CommandHandler
from telegram.error import BadRequest, TelegramError, RetryAfter

class DBStore:
    '''
    Handles all database related actions for this program.
    '''
    
    def __init__(self, host='localhost', port='5432', user='user', password='pass', dbname='test'):
        '''
        Initialization parameters:
        host - the hostname or ip address of the server (Ex: localhost, 192.168.75.23)
        port - the port of the database server
        user - an authorized username who is allowed to access/modify the databse
        password - the password for the user
        dbname - the name of the database
        
        The same can be configured using an environment variable in the format,
        DATABASE_URL = "postgres://user:password@host:port/dbname"
        '''
        
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Check if 'DATABASE_URL'  environment variable exists and use it confugure for database access
        from os import environ
        if ('DATABASE_URL' in environ and len(environ['DATABASE_URL'])!=0 and (
            environ['DATABASE_URL'].startswith('postgresql://') or environ['DATABASE_URL'].startswith('postgres://'))):
            self.logger.debug("Detected DATABASE_URL: {0}".format(environ['DATABASE_URL']))
            try:
                url = environ['DATABASE_URL']
                urlp1 = url.split('/')[2].split('@')
                self.host = urlp1[1].split(':')[0]
                self.port = int(urlp1[1].split(':')[1])
                self.user = urlp1[0].split(':')[0]
                self.password = urlp1[0].split(':')[1]
                self.dbname = url.split('/')[3].split('?')[0]
            except Exception:
                self.logger.exception()
        # Else take the deafult values
        else:
            self.host = host
            self.port = port
            self.user = user
            self.password = password
            self.dbname = dbname
        
        self.logger.debug("Connecting Databse with: {0}".format({
            'host': self.host,
            'port': self.port,
            'user': self.user,
            'password': self.password,
            'dbname': self.dbname
            }))
        # Try out the connection to make sure it works and setup the 'ready' flag
        try:
            with pg.connect(database=self.dbname, user=self.user, password=self.password, host=self.host, port=self.port) as conn:
                self.ready = True
                self.logger.info("Databse connection works at: {0}@{1}:{2}/{3}".format(self.user, self.host, self.port, self.dbname))
        except pg.DatabaseError as err:
            self.logger.error("Failed to connect database! {0}".format(err))
            self.logger.warning("Not using data persistance!") # i.e We'll not store values like last tweet id or channel id
            self.ready = False
    
    def load_keystore(self, values):
        '''
        Loads all key-value pairs from the database into the above dict
        '''
        
        if type(values) != dict or not self.ready:
            return
        try:
            with pg.connect(database=self.dbname, user=self.user, password=self.password, host=self.host, port=self.port) as conn:
                with conn.cursor() as cur:
                    # Check if the table 'keystore' exists, only then read the values from it
                    cur.execute("SELECT to_regclass( %s ) IS NOT NULL;", ('keystore',))
                    if cur.fetchone()[0]:
                        cur.execute("SELECT * FROM keystore;")
                        for row in cur.fetchall():
                            values[row[1]] = row[2]
            self.logger.debug("Read from '{0}.{1}': {2}".format(self.dbname, 'keystore', values))
        except (pg.DatabaseError, pg.ProgrammingError, pg.OperationalError, pg.InternalError):
            self.logger.exception("Error while reading values from the database!")
    
    def save_keystore(self, values):
        '''
        Save the key-value pairs from the dict to the database
        '''
        
        if type(values) != dict or not self.ready:
            return
        try:
            with pg.connect(database=self.dbname, user=self.user, password=self.password, host=self.host, port=self.port) as conn:
                with conn.cursor() as cur:
                    # Check if the table 'keystore' exists, if not create it
                    cur.execute("SELECT to_regclass( %s ) IS NULL;", ('keystore',))
                    if cur.fetchone()[0]:
                        cur.execute("CREATE TABLE keystore(id SERIAL PRIMARY KEY, key TEXT NOT NULL, value TEXT);")
                        conn.commit()
                        
                    # for each set of (key,value) pairs, create/update the entry
                    for key in values.keys():
                        cur.execute("SELECT EXISTS(SELECT key FROM keystore WHERE key = %s);", (key,))
                        if cur.fetchone()[0]:
                            cur.execute("UPDATE keystore SET value = %s WHERE key = %s;", (values[key], key,))
                        else:
                            cur.execute("INSERT INTO keystore(key,value) VALUES (%s, %s);", (key, values[key],))
                    conn.commit()
            self.logger.debug("Written to '{0}.{1}': {2}".format(self.dbname, 'keystore', values))
        except (pg.DatabaseError, pg.ProgrammingError, pg.OperationalError, pg.InternalError):
            self.logger.exception("Error while writing values from the database!")
    
    def save_tmp_value(self, id, value):
        '''
        Create a temporary table and store the given id-value pair
        '''
        
        if(type(id) != int or not self.ready):
            return
        try:
            with pg.connect(database=self.dbname, user=self.user, password=self.password, host=self.host, port=self.port) as conn:
                with conn.cursor() as cur:
                    # Check if the table 'tmp' exists, if not create it
                    cur.execute("SELECT to_regclass( %s ) IS NULL;", ('tmp',))
                    if cur.fetchone()[0]:
                        cur.execute("CREATE TABLE tmp(id INTEGER PRIMARY KEY, value TEXT);")
                        conn.commit()
                        
                    # Store/Update the given id-value pair
                    cur.execute("SELECT EXISTS(SELECT id FROM tmp WHERE id = %s);", (id,))
                    if cur.fetchone()[0]:
                        cur.execute("UPDATE tmp SET value = %s WHERE id = %s;", (value, id,))
                    else:
                        cur.execute("INSERT INTO tmp(id,value) VALUES (%s, %s);", (id, value,))
                    conn.commit()
        except (pg.DatabaseError, pg.ProgrammingError, pg.OperationalError, pg.InternalError):
            self.logger.exception("Error while writing values from the database!")
    
    def get_tmp_value(self, id):
        if(type(id) != int or not self.ready):
            return
        try:
            with pg.connect(database=self.dbname, user=self.user, password=self.password, host=self.host, port=self.port) as conn:
                with conn.cursor() as cur:
                    # Check if the table 'tmp' exists, only then read the values from it
                    cur.execute("SELECT to_regclass( %s ) IS NOT NULL;", ('tmp',))
                    if cur.fetchone()[0]:
                        cur.execute("SELECT value FROM tmp WHERE id = %s ;", (id,))
                        return cur.fetchone()[0]
        except (pg.DatabaseError, pg.ProgrammingError, pg.OperationalError, pg.InternalError):
            self.logger.exception("Error while reading values from the database!")
    
    def drop_tmp(self):
        try:
            with pg.connect(database=self.dbname, user=self.user, password=self.password, host=self.host, port=self.port) as conn:
                with conn.cursor() as cur:
                    # Check if the table 'tmp' exists, only then drop/delete the table
                    cur.execute("SELECT to_regclass( %s ) IS NOT NULL;", ('tmp',))
                    if cur.fetchone()[0]:
                        cur.execute("DROP TABLE tmp;")
                    conn.commit()
        except (pg.DatabaseError, pg.ProgrammingError, pg.OperationalError, pg.InternalError):
            self.logger.exception("Error while deleting values from the database!")


class TelegramBot:
    '''
    Handles all telegram bot related actions
    '''
    
    def __init__(self, bot_api_key, channel_name, channel_id=None, welcome_text="No Service!"):
        '''
        Initialization parameters:
        bot_api_key - the telegram bot api key received after creating the bot with botfather
        channel_name - the username of the channel
        channel_id (optional) - If the channel id already exists, pass it on here
        welcome_text - a welcome text to show anyone who visits and starts the bot
        '''
        
        self.channel = channel_name
        self.channel_id = channel_id
        self.logger = logging.getLogger(self.__class__.__name__)
        
        self.logger.debug("Bot args: {0}".format({
            'channel': self.channel,
            'channel_id': self.channel_id,
            'welcome_text': welcome_text,
            'bot_api_key': bot_api_key
            }))
        
        def __on_bot_start(update, context):
            self.logger.info("Received request from user!")
            try:
                context.bot.send_message(chat_id=update.effective_chat.id, parse_mode='markdown', text=welcome_text)
            except RetryAfter:
                self.logger.warning("Rate-limited by the telegram api!")
        # Setup the telegram api
        try:
            self.updater = Updater(bot_api_key, use_context=True)
            start_handler = CommandHandler('start', __on_bot_start)
            self.updater.dispatcher.add_handler(start_handler)
            self.bot = self.updater.bot
            self.logger.debug("Connected telegram bot '{0}', state: {1}".format(self.updater.bot.name, 'RUNNING' if self.updater.running else 'DOWN'))
        except TelegramError:
            self.logger.exception("Error while setting up the telegram api!")
            self.logger.fatal("Unable to connect the telegram api!")
            exit(2)
    
    def start(self):
        '''
        Starts the bot
        '''
        
        if (not self.updater.running):
            self.updater.start_polling()
            self.logger.debug("Updater started polling! State:{0}".format('RUNNING' if self.updater.running else 'DOWN'))
            
            # Get channel id if it doesn't exit already, try for 10 times
            if (not self.channel_id):
                for i in range(1,11):
                    try:
                        self.channel_id = self.bot.get_chat("@{0}".format(self.channel)).id
                        break
                    except BadRequest as err:
                        self.logger.warning("Failed to get fetch channel id! ({0}) : {1}".format(i, err))
                        if (i == 10):
                            self.stop()
                            self.logger.fatal("No channel id, can't continue!!")
                            exit(2)
                    sleep(10)
            self.logger.info("Bot '{0}' running & online for channel '{1}:{2}'".format(self.updater.bot.name, self.channel, self.channel_id))
    
    def stop(self):
        '''
        Stops the bot (updater thread only)
        '''
        
        if (self.updater.running):
            self.updater.stop()
            self.logger.debug("Updater stopped! State:{0}".format('RUNNING' if self.updater.running else 'DOWN'))
            self.logger.info("Bot stopped!")
    
    def send_msg(self, msg):
        '''
        Send a message in the channel
        '''
        if(type(msg) != str):
            return
        try:
            self.bot.send_message(chat_id=self.channel_id, parse_mode='html', text=msg)
        except RetryAfter as err:
            # Rate limited! So, wait for some time and retry
            self.logger.warning("Rate-limited by the telegram api! Retrying after {0}s..".format(err.retry_after))
            sleep(err.retry_after)
            self.send_msg(msg)
        except BadRequest:
            self.logger.exception("Text: {0}".format(msg))


class TweetDrasta:
    '''
    Handles all twitter related actions
    '''
    
    RETWEET_EMOJI = chr(0x1F501) # Emoji Retweet: repeat 
    REPLY_EMOJI = chr(0x21AA)    # Emoji Reply: left arrow curving right
    
    def __init__(self, api_key, api_secret, username, bot, max_rollback=50, ratelimit_wait=(15*60), last_statusid=None):
        '''
        Initialization parameters:
        api_key - the twitter developer api key
        api_secret - the twitter developer api key
        bot - a TelegramBot object
        max_rollback - max limit no of tweets to roll back if not updated for a long time (depends on memory resources)
        ratelimit_wait - no of mins to wait if rate limited by the twitter api (default: 15)
        last_statusid (optional) - If the last status (tweet) id already exists, pass it on here
        '''
        
        self.username = username
        self.bot = bot
        self.max_rollback = max_rollback
        self.ratelimit_wait = ratelimit_wait
        self.last_statusid = last_statusid
        self.logger = logging.getLogger(self.__class__.__name__)
        
        self.logger.debug("Drasta args: {0}".format({
            'username': self.username,
            'max_rollback': self.max_rollback,
            'ratelimit_wait': self.ratelimit_wait,
            'last_statusid' : self.last_statusid,
            'api_key': api_key,
            'api_secret': api_secret
            }))
        
        # Setup the twitter api
        try:
            auth = tweepy.AppAuthHandler(api_key, api_secret)
            self.api = tweepy.API(auth)
            self.logger.debug("Connected to twitter!")
        except tweepy.TweepError:
            self.logger.exception("Failed to connect twitter api!")
            self.logger.fatal("Unable to connect twitter api!")
            exit(2)
        
    def __rtlimt(self, cursor):
        # Handles rate limit inside cursor
        while True:
            try:
                yield cursor.next()
            except tweepy.RateLimitError:
                self.logger.warning("Rate-limited by the twitter api! Retrying after {0}s..".format(self.ratelimit_wait))
                sleep(self.ratelimit_wait)
            except StopIteration:
                return
    
    def __rangem(self, mentions):
        j,k,i = 0,0,0
        for men in mentions:
            if i==0:
                j = men['indices'][0]
            elif mentions[i-1]['indices'][1]+1 != men['indices'][0]:
                break
            k = men['indices'][1]
            i += 1
        return (j,k)

    def status_str(self, status):
        # Formats the statuses into a string representation
        if(type(status) != tweepy.Status):
            return ''
        is_retweet = hasattr(status, 'retweeted_status')
        text = (status.retweeted_status.full_text if is_retweet else status.full_text) if hasattr(status, 'full_text') else status.text
        mentions = status.entities['user_mentions']
        str = ''
        if (is_retweet):
            mentions = status.retweeted_status.entities['user_mentions']
            mn = " {0} {1}".format(u'\u2192',' '.join(["@{0}".format(u['screen_name']) for u in status
                                                       .retweeted_status.entities['user_mentions']])) if len(mentions)!=0 else ""
            str += "{0}  <b>{1}{2}</b>\n{3}\n".format(self.RETWEET_EMOJI,status.retweeted_status.user.screen_name, mn,
                                                        text[self.__rangem(mentions)[1]:].strip())
        elif (status.in_reply_to_screen_name and len(mentions)!=0):
            mn = ' '.join(["@{0}".format(u['screen_name']) for u in mentions])
            str += "{0}  <b>{1}</b>\n{2}\n".format(self.REPLY_EMOJI, mn, text[self.__rangem(mentions)[1]:].strip())
        else:
            str += "{0}\n".format(text)
        str += "https://twitter.com/{0}/status/{1}\n{2}\n".format(status.user.screen_name, status.id, status.created_at.strftime("%A, %B %e %Y at %I:%M%p"))
        return str
    
    def __get_statuses_since(self, since_id):
        sts = []
        if since_id == None:
            return sts
        i = 0
        for statuses in self.__rtlimt(tweepy.Cursor(self.api.user_timeline, id=self.username).iterator):
            for status in statuses:
                if (status.id <= since_id or i >= self.max_rollback) :
                    return sts
                sts.append(status.id)
                i += 1
        return sts
    
    def __get_status_by_id(self, id):
        try:
            return self.api.get_status(id, tweet_mode='extended')
        except tweepy.RateLimitError:
            self.logger.warning("Rate-limited by the twitter api! Retrying after {0}s..".format(self.ratelimit_wait))
            sleep(self.ratelimit_wait)
            return self.__get_status_by_id(id)
        except tweepy.TweepError:
            self.logger.exception("Error while fetching tweet for id: {0}".format(id))
        return None
    
    def __check_status(self, status):
        if(status == None):
            return
        if(status.truncated or (hasattr(status, 'retweeted_status') and status.retweeted_status)):
            status = self.__get_status_by_id(status.id)
        return status
    
    def update_status(self):
        count = 0
        try:
            # Get recent 20 tweets
            recent_status = list(self.__rtlimt(tweepy.Cursor(self.api.user_timeline, id=self.username).items(20)))
            ids = [st.id for st in recent_status]
            self.logger.debug("Fetched {0} recent statuses! last_statusid: '{1}'".format(len(recent_status), self.last_statusid))
            if (self.last_statusid == None):
                # If there's no last status update the first one
                status = recent_status[0]
                self.bot.send_msg(self.status_str(self.__check_status(status)))
                self.last_statusid = status.id
                count += 1
            elif (self.last_statusid in ids):
                # If last status is present in the current top 20, update all since the last one
                self.logger.debug("Got last_statusid in recent_status!")
                for status in reversed(recent_status[:ids.index(self.last_statusid)]):
                    self.bot.send_msg(self.status_str(self.__check_status(status)))
                    self.last_statusid = status.id
                    count += 1
                    sleep(3)
            else:
                # Else roll back to find the last status and update all since then
                self.logger.debug("last_statusid not in recent_status! Rolling back to seek last_statusid!")
                for status_id in reversed(self.__get_statuses_since(self.last_statusid)):
                    status = self.__get_status_by_id(status_id)
                    if status :
                        self.bot.send_msg(self.status_str(status))
                        self.last_statusid = status.id
                        count += 1
                        sleep(3)
            if count > 0:
                self.logger.info("Updated {0} statuses!".format(count))
            self.logger.debug("Updated {0} statuses!".format(count))
        except tweepy.TweepError:
            self.logger.exception("Error while updating recent tweets!")
    
    def dig_update(self, dbstore, count, all):
        # Digs and updates all last N(count) tweets or all tweets from the user 
        if(not dbstore.ready):
            self.logger.error("Can't process this request without the database! Make sure the postgresql database is up and configured!")
            return
        self.logger.info("Digging! count: {0}, all: {1}".format(count, all))
        
        i,f,r,c = 0,(count//20),(count%20),0
        last = None
        try:
            # Get N tweets or all tweets and store them in tmp database store
            for statuses in self.__rtlimt(tweepy.Cursor(self.api.user_timeline, id=self.username).iterator):
                if (not all and f-i<=0 and r>0):
                    statuses = statuses[:r]
                stx = [self.status_str(self.__check_status(status)) for status in statuses]
                i += 1
                c += len(stx)
                last = statuses[-1].id
                if i == 1 :
                    self.last_statusid = statuses[0].id
                
                dbstore.save_tmp_value(i, json.dumps(stx))
                print("Fetched: {0}".format(c), end='\r')
                if (not all and i >= f):
                    break
            self.logger.info("Fetched {0} tweets!".format(c))
            
            # Update all tweets from the database to the telegram channel
            c = 0
            while i>0:
                stx = dbstore.get_tmp_value(i)
                try:
                    stx = list(json.loads(stx))
                except json.JSONDecodeError:
                    self.logger.warning("Got corrupt json from the server!")
                    i -= 1
                    continue
                for st in reversed(stx):
                    self.bot.send_msg(st)
                    sleep(3)
                i -= 1
                c += len(stx)
                print("Updated: {0}".format(c), end='\r')
            self.logger.info("Updated {0} tweets!".format(c))
        except tweepy.TweepError:
            self.logger.exception()
        finally:
            dbstore.drop_tmp()
        return last


class Config:
    '''
    A model to server attributes of the config file
    '''
    
    def __init__(self, filename):
        '''
        Initialization parameters:
        filename - path to the json formatted config file
        '''
        
        self.logger = logging.getLogger(self.__class__.__name__)
        self.filename = filename
        self.logger.info("Config file: {0}".format(filename))
        self.load()
    
    def load(self):
        '''
        loads/reloads the attributes from the config file to this class
        '''
        config = {}
        try:
            with open(self.filename, 'r') as f:
                config = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError, PermissionError)  as err:
            self.logger.exception("Failed to read config: {0}".format(err))
            self.logger.fatal("Failed to read the config file!")
            exit(2)
        self.__json = config
        self.logger.debug("Config: {0}".format(self.__json))
        
        for k,v in config.items():
            setattr(self, k, v)


class App:
    def __init__(self, cfg):
        self.config = cfg
        self.stop = False
        self.running = False
        self.persist = {}
        self.logger = logging.getLogger(self.__class__.__name__)
        
        self.dbstore = DBStore(dbname=cfg.db_name, host=cfg.db_host, port=cfg.db_port,
                               user=cfg.db_user, password=cfg.db_password) if (hasattr(cfg, 'db_name') and hasattr(
                                   cfg, 'db_host') and hasattr(cfg, 'db_port') and hasattr(cfg, 'db_user') and hasattr(cfg, 'db_password')) else DBStore()
        self.dbstore.load_keystore(self.persist)
        
        for key in ['twitter_username', 'twitter_apikey', 'twitter_api_secret', 'telegram_channel', 'telegram_bot_apikey']:
            if not (hasattr(cfg, key)):
                self.__exit_hook(2, "Error: '{0}' not present in config!".format(key))
                
        
        self.bot = TelegramBot(bot_api_key=cfg.telegram_bot_apikey, channel_name=cfg.telegram_channel,
                               channel_id=(int(self.persist['channel_id']) if 'channel_id' in self.persist else None), 
                               welcome_text=(cfg.welcome_text if hasattr(cfg, 'welcome_text') else 'Hi! Join @{0}'.format(cfg.telegram_channel)))
        
        self.drasta = TweetDrasta(cfg.twitter_apikey, cfg.twitter_api_secret, cfg.twitter_username, self.bot,
                             last_statusid=(int(self.persist['last_statusid']) if 'last_statusid' in self.persist else None), 
                             max_rollback=(int(cfg.max_rollback) if hasattr(cfg, 'max_rollback') else 50), 
                             ratelimit_wait=(int(cfg.ratelimit_wait)*60 if hasattr(cfg, 'ratelimit_wait') else 15*60))
        try:
            if hasattr(cfg, 'retweet_emoji'):
                self.drasta.RETWEET_EMOJI = chr(int(cfg.retweet_emoji, 16) if str(cfg.retweet_emoji).lower().startswith('0x') else int(cfg.retweet_emoji))
            if hasattr(cfg, 'reply_emoji'):
                self.drasta.REPLY_EMOJI = chr(int(cfg.reply_emoji, 16) if str(cfg.reply_emoji).lower().startswith('0x') else int(cfg.reply_emoji))
        except Exception:
            pass
        self.seek_rate = int(cfg.seek_rate)*60 if hasattr(cfg, 'seek_rate') else 60
        
        def __exit_notify(signal, frame):
            self.logger.info("Received Terminate signal!")
            if not self.running or self.stop:
                self.__exit_hook(1)
            self.stop = True
        signal.signal(signal.SIGINT, __exit_notify)
        signal.signal(signal.SIGTERM, __exit_notify)
    
    def __start_hook(self):
        self.bot.start()
        self.persist['channel_id'] = self.bot.channel_id
        self.dbstore.save_keystore(self.persist)
    
    def __stop_hook(self):
        self.bot.stop()
    
    def __update_hook(self):
        self.drasta.update_status()
        self.persist['last_statusid'] = self.drasta.last_statusid
        self.dbstore.save_keystore(self.persist)
    
    def __exit_hook(self, exitcode, reason="Stopped!"):
        self.__stop_hook()
        self.logger.info(str(reason))
        exit(exitcode)
    
    def dig(self, count=0, all=False):
        self.__start_hook()
        self.bot.stop()
        res = self.drasta.dig_update(dbstore=self.dbstore, count=count, all=all)
        self.persist['last_statusid'] = self.drasta.last_statusid
        self.dbstore.save_keystore(self.persist)
        return res
    
    def main(self):
        self.__start_hook()
        while not self.stop:
            self.running = True
            self.__update_hook()
            self.running = False
            if self.stop :
                self.__exit_hook(0)
            sleep(self.seek_rate)
        self.__exit_hook(0)


if __name__ == '__main__':
    parser = ArgumentParser(description="Helps forwarding Twitter messages to a Telegram channel")
    parser.add_argument('-g', '--dig', help="Dig and update last N tweets", dest='dig', nargs=1, type=int, default=[0])
    parser.add_argument('-w', '--dig-all', help="Dig and update all tweets", action='store_true', dest='dig_all')
    parser.add_argument('-c', '--config', help="Config file (default: config.json)", dest='config', nargs=1, type=str, default=['config.json'])
    parser.add_argument('-d', '--debug', help="Enable debug", action='store_true', dest='debug')
    parser.add_argument('-V', '--version', action='version', version='%(prog)s 0.1')
    args = parser.parse_args()
    
    logging.basicConfig(format='%(asctime)s %(levelname)-8s %(name)-12s - %(message)s', level=(logging.DEBUG if args.debug else logging.INFO))
    
    cfg = Config(args.config[0])
    app = App(cfg)
    
    if args.dig[0] > 0 :
        print("Last tweet id: {0}".format(app.dig(count=int(args.dig[0]))))
    elif args.dig_all :
        print("Last tweet id: {0}".format(app.dig(all=True)))
    else:
        app.main()

