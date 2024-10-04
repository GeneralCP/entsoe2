"""
Querying dayahead electricity prices from ENTSO-E with pure Python.
Entsoe-py is very cool, covering all ENTSO-E features, but it builds upon > 10 (transitive) dependencies (including huge
ones such as numpy) which isn't maybe that nice when running on a Raspberry Pi.
"""

from datetime import datetime, timedelta, timezone
from urllib.request import urlopen
from xml.etree import ElementTree
import pandas as pd


def get_dayahead_prices(api_key: str, area_code: str, start: datetime = None, end: datetime = None, df=0, tz='UTC'):
    """
    Get https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html 4.2.10. Day Ahead Prices [12.1.D]
    * One year range limit applies
    * Minimum time interval in query response is one day
    :param api_key: https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html#_authentication_and_authorisation
    :param area_code: https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html#_areas
    :param start: Start date(time) for the query. If no tzinfo is defined, UTC is assumed. Default = now.
    :param end: End date(time) for the query. If no tzinfo is defined, UTC is assumed. Default = start + 1 day ahead.
    :param df: default a dictionary is returned. if df=1 then a pandas series is returned
    :param tz: default UTZ timezone is returned. otherwise specify timezone. only works for dataframes
    :return: Dictionary (ordered on Python 3.6+) of mappings {datetime(UTC) : price(EUR/MWH)}, *as returned by
    ENTSO-E, not strictly bound by start/end.* ENTSO-E returns whole day(s), and due to time zone boundaries the result
    might also contain end of yesterday, beginning of the day after tomorrow, etc.
    """
    if not start:
        start = datetime.now().astimezone(timezone.utc)
    elif start.tzinfo and start.tzinfo != timezone.utc:
        start = start.astimezone(timezone.utc)
    if not end:
        end = start + timedelta(days=1)
    elif end.tzinfo and end.tzinfo != timezone.utc:
        end = end.astimezone(timezone.utc)

    fmt = '%Y%m%d%H00'  # Somehow minutes must be 00, otherwise "HTTP 400 bad request" is returned.
    # GET /api?documentType=A44&in_Domain=10YCZ-CEPS-----N&out_Domain=10YCZ-CEPS-----N&periodStart=201512312300&periodEnd=201612312300
    url = f'https://web-api.tp.entsoe.eu/api?securityToken={api_key}&documentType=A44&in_Domain={area_code}' \
          f'&out_Domain={area_code}&periodStart={start.strftime(fmt)}&periodEnd={end.strftime(fmt)}'

    with urlopen(url) as response:  # Raises URLError
        if response.status != 200:
            raise Exception(f"{response.status=}")
        xml_str = response.read().decode()

    result = {}
    for child in ElementTree.fromstring(xml_str):
        if child.tag.endswith("TimeSeries"):  # endswith to ignore namespace
            for ts_child in child:
                if ts_child.tag.endswith("Period"):
                    for pe_child in ts_child:
                        if pe_child.tag.endswith("timeInterval"):
                            for ti_child in pe_child:
                                if ti_child.tag.endswith("start"):
                                    # There's no canonical way to parse ISO formatted dates. datetime.fromisoformat doesn't work. This works.
                                    start_time = datetime.strptime(ti_child.text, '%Y-%m-%dT%H:%MZ').replace(tzinfo=timezone.utc)
                        elif pe_child.tag.endswith("Point"):
                            for po_child in pe_child:
                                if po_child.tag.endswith("position"):
                                    delta = int(po_child.text) - 1  # 1...24 to zero-indexed
                                    time = start_time + timedelta(hours=delta)
                                elif po_child.tag.endswith("price.amount"):
                                    price = float(po_child.text)
                                    result[time] = price

    if df==1:
        result = pd.Series(result).tz_convert(tz)

    return result