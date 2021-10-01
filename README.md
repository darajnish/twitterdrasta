# TwitterDrasta

Helps forwarding [Twitter](https://twitter.com/) messages from a public twitter handle to a [Telegram](https://telegram.org/) channel



This bot can be used to check for recent tweets by a public twitter handle and forward it over a Telegram channel, using the Telegram bot API.

### Features

* Forward all recent tweets from a public Twitter handle to a Telegram channel
* Auto rollback to update tweets from the last tweet, if the bot was down for a few hours
* Can dig and update last N no of tweets or even all possible tweets
* Rate limit handled protection on Twitter and Telegram API
* [Heroku](https://www.heroku.com/) dynos compatible
* Support for custom tweet formatting over telegram

## Requirements

##### For running the script

- [Python](https://www.python.org/downloads/) 3.8 or above
- [pip](https://pip.pypa.io/en/stable/installing/) 20.1 or above (To installs the dependencies below)
- [Tweepy](https://github.com/tweepy/tweepy) 3.9 or above
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) 12.8 or above
- [psycopg2](https://github.com/psycopg/psycopg2) 2.8 or above

##### For making the bot work

- [Twitter developer](https://developer.twitter.com/) API key and API secret: 
- Twitter public handle's username
- [Telegram Bot](https://core.telegram.org/bots#3-how-do-i-create-a-bot) API key
- [Telegram Channel](https://telegram.org/tour/channels) Username/ID
- [PostgreSQL Server](https://www.postgresql.org/download/) (Optional: only for persistence of last tweet, and for digging and updating old tweets)

## Running

First, install the required dependencies if you haven't already installed. The last three dependencies can be installed using **pip** (using a terminal in this directory) as follows.

```bash
pip install -r requirements.txt
```



Now, create a json based config file for the program, with all required values for all API keys and usernames (put usernames without '@'). The example config file `config.json.example` will help you making your own config file, make sure the config file is in json format and ends with `.json` file extension. For ex: `my-config.json`, `/some/path/my-config.json`(default: `config.json`, in the same directory as the script)

**Example config.json**

```json
{
    "twitter_username" : "PASTE-THE-TWITTER-USERNAME-HERE",
    "twitter_apikey" : "PASTE-THE-TWITTER-API-KEY-HERE",
    "twitter_api_secret" : "PASTE-THE-TWITTER-API-SECRET-HERE",
    "telegram_channel" : "PASTE-THE-TELEGRAM-CHANNEL-USERNAME-HERE",
    "telegram_bot_apikey" : "PASTE-THE-TELEGRAM-BOT-API-KEY-HERE",
    "seek_rate" : 2,
    "max_rollback" : 200,
    "ratelimit_wait" : 16,
    "welcome_text" : "WRITE-A-WELCOME-MESSAGE-FOR-ANYONE-WHO-STARTS-THE-TELEGRAM-BOT",
    "tweet_format" : "{text}\n{url}\n{time}\n",
    "reply_format" : "\u21aa <b>{mentions}</b>\n{text}\n{url}\n{time}\n",
    "retweet_format" : "\ud83d\udd01  <b>{username}{mentions}</b>\n{text}\n{url}\n{time}\n"
}
```


**Config Values**


| **Key**               | **Description**                                                                         |
|:---------------------:|-----------------------------------------------------------------------------------------|
| `twitter_username`    | Twitter username of the public handle without `@`                                       |
| `twitter_apikey`      | Twitter developer API Key                                                               |
| `twitter_api_secret`  | Twitter developer API Secret                                                            |
| `telegram_channel`    | Telegram channel username                                                               |
| `telegram_bot_apikey` | Telegram Bot API Key                                                                    |
| `seek_rate`           | The time in minutes to wait before seeking newer tweets and upadating on telegram       |
| `max_rollback`        | Maximum no of previous tweets to obtain if the last tweet is not a recent one           |
| `ratelimit_wait`      | The time in minutes to wait before trying again when rate-limited by the Twitter server |
| `welcome_text`        | Simple welcome / greeting text for the users who visit the Telegram Bot                 |
| `tweet_format`        | Formatting for any normal tweet text which would be sent to the Telegram Channel        |
| `reply_format`        | Formatting for the tweet text that is a reply to some other tweet                       |
| `retweet_format`      | Formatting for the tweet text that is a retweet of some other tweet                     |



Next, Make sure the PostgreSQL server is setup with a username and password and it's running (if you want to use the database).

The bot can be configured to use the database server either by hardcoding the values, or through defining `DATABASE_URL` as environment variable which holds the URI for the postgresql database.

The format for URI for `DATABASE_URL` should be like,

```html
postgres://<user>:<password>@<hostname>:<port>/<database>
```




With all setup, start the bot feeding the path of your config file,

```bash
python TwitterDrasta.py --config /some/path/my-config.json
```

**OR**

```bash
python TwitterDrasta.py --config my-config.json
```



Running using the `DATABASE_URL` environment variable on the same line,

```bash
DATABASE_URL="postgres://<user>:<password>@<hostname>:<port>/<database>" python TwitterDrasta.py --config my-config.json
```



#### Setting up on Heroku

The bot is already compatible with heroku dynos, and this repository already contains files for **heroku/python** buildpack, `requirements.txt`, `runtime.txt` and `Procfile`.

Just create a config file as told above and update the config filename in `Procfile` arguments (default filename: `config.json`) and push the contents to heroku git.



#### Digging and Updating old tweets

This operations is not automatic and it requires a configured PostgreSQL Server running. Make sure `DATABASE_URL` is defined in the environment variables or the database configurations are hardcoded into the script.

And, this operation may take a lot of time, if the no of tweets to be dug are high.



To dig and update last N no of tweets,

```bash
python TwitterDrasta.py --config my-config.json -g N
```

To dig and update all possible tweets,

```bash
python TwitterDrasta.py --config my-config.json -w
```



#### Debugging

To run the bot in debug mode, just pass the flag `-d`  or `--debug` in the arguments.

```bash
python TwitterDrasta.py --debug --config my-config.json
```



## Contributing

All kinds of contributions towards the improvement and enhancement of this project are welcome. Any valuable pull request for fixing an issue or enhancing the project are welcome. You can even help by [reporting bugs](https://github.com/darajnish/twitterdrasta/issues/new/choose) and creating issues for suggestions and ideas related to new improvements and enhancements.

## License

This project is under the [MIT License](LICENSE)
