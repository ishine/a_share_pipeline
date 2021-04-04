import datetime
import time


def time_point(time_format='%Y%m%d_%H%M%S'):
    return time.strftime(time_format, time.localtime())


def get_datetime_from_date_str(str_date):
    """
    由日期字符串获得datetime对象
    :param str_date: 日期字符串，格式 2021-10-20
    :return: datetime对象
    """
    year_temp = str_date.split('-')[0]
    month_temp = str_date.split('-')[1]
    day_temp = str_date.split('-')[2]
    return datetime.date(int(year_temp), int(month_temp), int(day_temp))


def get_next_work_day(datetime_date, next_flag=1):
    """
    获取下一个工作日
    :param datetime_date: 日期类型
    :param next_flag: -1 前一天，+1 后一天
    :return: datetime.date
    """
    if next_flag > 0:
        next_date = datetime_date + datetime.timedelta(
            days=7 - datetime_date.weekday() if datetime_date.weekday() > 3 else 1)
    else:
        # 周二至周六
        if 0 < datetime_date.weekday() < 6:
            next_date = datetime_date - datetime.timedelta(days=1)
            pass
        elif 0 == datetime_date.weekday():
            # 周一
            next_date = datetime_date - datetime.timedelta(days=3)
        else:
            # 6 == datetime_date.weekday():
            # 周日
            next_date = datetime_date - datetime.timedelta(days=2)
            pass
        pass
    return next_date


def get_today_date():
    # 获取今天日期
    time_format = '%Y-%m-%d'
    return time.strftime(time_format, time.localtime())