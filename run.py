#!/usr/bin/env python3

import requests
import argparse
import re
import logging
import time
from bs4 import BeautifulSoup
from slackclient import SlackClient


schedule_url = 'http://m.cgv.co.kr/Schedule/cont/ajaxMovieSchedule.aspx'
movieidx_url = 'http://m.cgv.co.kr/WebApp/MovieV4/movieDetail.aspx?cgvCode={}'
movieinfo_url = 'http://www.cgv.co.kr/movies/detail-view/?midx={}'
theater_url = 'http://m.cgv.co.kr/WebApp/TheaterV4/TheaterDetail.aspx?tc={}'
# Copied from https://github.com/maplejune/nightwatch-imax/blob/master/nightwatch_imax/schedule.py
# Expected format
# popupSchedule(movieName, screenName, startTime, remainSeat, capacitySeat, CGVCode, movieIdx, PlayYMD, PlayNum,
#               ScreenCd, PlayTimeCd, Rating, ScreenRatingCd, ScreenRatingNm, StartHHMM, KidsScreenType,
#               strPLAY_END_TM, strPLATFORM_NM, strMOVIE_RATING_NM, strPLAY_TIME_NM, strMOVIE_PKG_YN,
#               strMOVIE_NOSHOW_YN, platformCd)
# Capture startTime, remainSeat, capacitySeat
MOVIE_CODE_PATTERN = re.compile("popupSchedule\('.*','.*','(\d\d:\d\d)','(\d*)','(\d*)',")
logging.basicConfig(format='%(asctime)s:%(message)s', level=logging.INFO)
logger = logging.getLogger()


class ScheduleInfo:
    starttime = ''
    remain = ''
    capacity = ''
    valid = False

    def __init__(self, rawhtml):
        info = MOVIE_CODE_PATTERN.search(str(rawhtml))
        if info is not None:
            self.starttime = info.group(1)
            self.remain = info.group(2)
            self.capacity = info.group(3)
            self.valid = True

    def __str__(self):
        if self.valid:
            return f'{self.starttime} {self.remain}/{self.capacity}'
        else:
            return ''


def query_schedule(theater_code, movie_code, date, screen_code):
    schedule_response = requests.post(
            schedule_url,
            data={'theaterCd': theater_code, 'playYMD': date, 'src': screen_code}
            ).text
    soup = BeautifulSoup(schedule_response, 'html.parser')
    schedule_list = []
    for a in soup.find_all('a'):
        s = ScheduleInfo(a)
        if s.valid:
            schedule_list.append(s)
    return '\n'.join([str(x) for x in schedule_list])


def send_message(sc, channelID, message):
    if sc is None:
        return
    if channelID == '':
        return
    sc.api_call(
            'chat.postMessage',
            channel=channelID,
            text=str(message)
            )


def get_theater_name(code):
    soup = BeautifulSoup(requests.get(theater_url.format(code)).text, 'html.parser')
    title_div = soup.select('#headerTitleArea')
    if len(title_div) == 1:
        return title_div[0].text
    else:
        logger.warning(f'Title div is not unique. {title_div}')
        return str(code)


def get_movie_name(code):
    movieinfo_res = requests.get(movieidx_url.format(code)).text
    soup = BeautifulSoup(movieinfo_res, 'html.parser')
    movieidx = soup.select('#fanpageMovieIdx')
    if len(movieidx) != 1:
        logger.warning(f'Cannot find unique movie idx. {movieidx}')
        return str(code)
    movieidx = movieidx[0]['value']
    soup = BeautifulSoup(requests.get(movieinfo_url.format(movieidx)).text, 'html.parser')
    moviename = soup.find('div', 'title').find('strong').text
    return moviename


def watch(theatercode, moviecode, date, screencode, slacktoken, slackchannel, period):
    moviename = get_movie_name(moviecode)
    theatername = get_theater_name(theatercode)
    sc = None
    if args.slacktoken != '':
        sc = SlackClient(slacktoken)
    cnt = 0
    if sc is not None:
        msg = f'Start monitoring for {moviename} in {theatername} with screencode {screencode} on {date}'
        send_message(sc, slackchannel, msg)
    while cnt < 10:
        schedule = query_schedule(theatercode, moviecode, date, screencode)
        logger.info(f'\n{schedule}')
        if len(schedule) != 0:
            cnt += 1
            if sc is not None:
                send_message(sc, args.slackchannel, f'Found schedule for {args.date}!\n{schedule}')
        time.sleep(period)
    send_message(sc, slackchannel, 'Found schedule 10 times! quiting')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--theatercode', type=str, required=True, help='Theater code')
    parser.add_argument('-m', '--moviecode', type=str, required=True, help='Movie code')
    parser.add_argument('-d', '--date', type=str, required=True, help='Date in YYYYMMDD format')
    parser.add_argument('-s', '--screencode', type=str, required=True, help='Screen code')
    parser.add_argument('--slacktoken', type=str, default='', help='Slack API Token')
    parser.add_argument('--slackchannel', type=str, default='', help='Slack channel')
    parser.add_argument('--period', type=int, default=60, help='Repeat time in seconds')
    args = parser.parse_args()

    watch(args.theatercode, args.moviecode, args.date, args.screencode, args.slacktoken, args.slackchannel, args.period)
