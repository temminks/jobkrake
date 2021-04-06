import json
import re
import time
import traceback
from dataclasses import asdict
from typing import Any
from typing import Callable, Tuple, Dict, List, Union

import aiohttp as aiohttp
import requests
from bs4 import BeautifulSoup

from sources.jobs import Job

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:84.0) Gecko/20100101 Firefox/84.0',
    'Accept': '*/*',
    'Accept-Language': 'de,en-US;q=0.7,en;q=0.3',
    'Content-Type': 'application/json;charset=utf-8',
    'Connection': 'keep-alive',
}


def fetch_jobs(func: Callable):
    """Decorator to catch some errors and to provide some timing."""

    async def wrapper() -> Tuple[Dict[str, List[Dict[str, Union[Exception, List, str]]]], float]:
        start_t = time.time()
        result: Dict[str, List[Dict[str, Union[Exception, List, str]]]] = dict()
        try:
            job_list: Dict[str, List[Job]] = await func()
            for company, jobs in job_list.items():
                result = {company: [asdict(job) for job in jobs]}
        except Exception:
            result = {func.__name__: [{"error": str(traceback.format_exc())}]}
        end_t = time.time()
        return result, end_t - start_t

    return wrapper


def parse_personio(json_response: List, career_url: str, company: str) -> List[Job]:
    desired_keys = {
        'name': 'title',
        'employment_type': 'type_',
        'seniority': 'seniority',
        'keywords': 'keywords',
        'office': 'location',
        'schedule': 'schedule',
        'department': 'department',
        'id': 'url',
    }
    result = list()
    for job in json_response:
        actual_keys = set(job.keys())
        key_set = set(desired_keys.keys()).intersection(actual_keys)
        data = {desired_keys[key]: job[key] for key in key_set}
        # make some adjustments to the parsed output and augment data
        data.update({
            'career_url': career_url,
            'company': company,
            'url': career_url + "job/" + str(data['url']),
            'keywords': [key.strip() for key in data['keywords'].split(',')],
        })
        result.append(Job(**data))
    return result


async def parse_rexx(url: str, payload: str, career_url: str, company: str) -> List[Job]:
    payload = 'reset_search=0&search_mode=job_filter_advanced&filter%5Bvolltext%5D=' + payload
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        session.headers.update({'Content-Type': 'application/x-www-form-urlencoded', })

        async with session.post(url, data=payload) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
            job_table = soup.find('table', {'id': 'joboffers'})
            jobs = job_table.findAll('tr', class_=re.compile('alternative_'))

    return [Job(**{
        "url": job.find('a')['href'],
        "title": job.find('a').text.strip(),
        "location": [loc.strip() for loc in job.find('td', class_='real_table_col2').text.split(',')],
        "keywords": [key.strip() for key in job.find('td', class_='real_table_col3').text.split(',')],
        "career_url": career_url,
        "company": company,
    }) for job in jobs]


async def parse_workday(url: str, payload: str, career_url: str, company: str) -> List[Job]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        session.headers.update({'Content-Type': 'application/x-www-form-urlencoded', })
        async with session.post(url + '1/replaceFacet/318c8bb6f553100021d223d9780d30be', data=payload) as response:
            jobs = json.loads(await response.text())['body']['children'][0]['children'][0]['listItems']
            return [Job(**{
                'title': job['title']['instances'][0]['text'],
                'url': url[:url.find('.com') + 4] + job['title']['commandLink'],
                'career_url': career_url,
                'company': company,
            }) for job in jobs]


def nttData_get_num_pages(soup: BeautifulSoup) -> int:
    num_pages = 1
    footer = soup.find('ul', class_='pagination')
    if footer:
        num_pages = len(footer.findAll('li', class_='page-item')) - 1
    return num_pages


def nttData_get_jobs(soup: BeautifulSoup, career_url: str, company: str) -> List[Job]:
    job_results = soup.find('div', class_='job-search-results')
    jobs = job_results.findAll('a', 'job-detail-link')

    return [Job(**{
        "url": "https://de.nttdata.com" + job['href'],
        "title": job.find('div', class_='col-md-6').text,
        "location": [loc.strip() for loc in job.find('div', class_='col-md-3').text.split(',')],
        "keywords": [word.strip() for word in job.findAll('div', class_='col-md-3')[1].text.split(",")],
        "career_url": career_url,
        "company": company,
    }) for job in jobs]


@fetch_jobs
async def vivavis() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://karriere.vivavis.com/"
        url = "https://rmk-map-12.jobs2web.com/services/jobmap/jobs?siteid=/rAdNpAjV4ECTWPiGDiQ3g==&mapType=GOOGLE_MAP&coordinates=48.9277,8.3989"
        async with session.get(url) as response:
            data = json.loads(await response.text())
            return {"vivavis": [Job(**{
                "title": d["title"],
                "location": list({"Ettlingen", d["city"]}),
                "date": d["referencedate"],
                "url": d["url"],
                "career_url": career_url,
                "company": "VIVAVIS AG",
            }) for d in data]}


@fetch_jobs
async def adesso() -> Dict[str, List[Job]]:
    career_url = "https://www.adesso.de/de/jobs-karriere/unsere-stellenangebote/stellenangebote.html"
    url = "https://www.adesso.de/de/jobs-karriere/unsere-stellenangebote/stellenangebote.html"
    payload = '&filter%5Bcountr%5D%5B%5D=Deutschlandweit&filter%5Bcountr%5D%5B%5D=Karlsruhe&filter%5Btaetigkeit_id%5D%5B%5D=4&filter%5Btaetigkeit_id%5D%5B%5D=3'
    return {"adesso": await parse_rexx(url, payload, career_url, company='adesso SE')}


@fetch_jobs
async def esentri() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://esentri.jobs.personio.de/"
        url = "https://esentri.jobs.personio.de/search.json"
        async with session.get(url) as response:
            data = json.loads(await response.text())
            jobs: List[Job] = parse_personio(data, career_url, company='esentri AG')
            return {"esentri": jobs}


@fetch_jobs
async def jacob_elektronik() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://jacob-elektronik.jobs.personio.de/"
        url = "https://jacob-elektronik.jobs.personio.de/search.json"
        async with session.get(url) as response:
            data = json.loads(await response.text())
            result = parse_personio(data, career_url, company='JACOB Elektronik GmbH')
            jobs: List[Job] = [job for job in result if "Karlsruhe" in job.location]
            return {"jacob_elektronik": jobs}


@fetch_jobs
async def appshere() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://appsphere-karriere.de/"
        url = "https://appsphere-karriere.de/"
        async with session.get(url) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
            sections = soup.main.findAll('section', class_='jobs')
            jobs = [section.findAll('div', class_='elementor-widget-button') for section in sections]
            jobs = [job for sublist in jobs for job in sublist]
            jobs = [job for job in jobs if 'elementor-hidden-desktop' not in job['class']]
            jobs = [job.find('a') for job in jobs]
            return {"appshere": [Job(**{
                "career_url": career_url,
                "title": job.text.strip(),
                "url": job['href'],
                "company": 'AppSphere AG',
            }) for job in jobs]}


@fetch_jobs
async def oxaion() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://karriere.modul-a-gruppe.com/stellenangebote.html?filter[client_id]=1&filter[countr]=Ettlingen"
        url = "https://karriere.modul-a-gruppe.com/stellenangebote.html?filter[client_id]=1&filter[countr]=Ettlingen"
        async with session.get(url) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
            containers = soup.find('div', {'id': 'joboffers'}).findAll('div', class_='joboffer_container')
            return {"oxaion": [Job(**{
                "url": container.find('div', class_='joboffer_title_text').find('a')['href'],
                "title": container.find('div', class_='joboffer_title_text').find('a').text,
                "location": [loc.strip() for loc in
                             container.find('div', class_='joboffer_informations').text.split(',')],
                "career_url": career_url,
                "company": "oxaion gmbh",
            }) for container in containers]}


@fetch_jobs
async def softproject() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        session.headers.update({'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', })

        career_url = "https://softproject.de/de/softproject/karriere/"
        url = "https://softproject.de/de/wp-admin/admin-ajax.php"
        payload = "action=loadmore&paged=0&listings_per_page=99"
        async with session.post(url, data=payload) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
            items = [item.div for item in soup.findAll('div', class_='awsm-job-listing-item')]
            return {"softproject": [Job(**{
                "url": item.find('div', class_='awsm-list-left-col').find('a')['href'],
                "title": item.find('div', class_='awsm-list-left-col').find('a').text,
                "location": [job.text.strip() for job in
                             item.find('div', class_='awsm-job-specification-job-location').findAll('span')],
                "seniority": item.find('div', class_='awsm-job-specification-erfahrung').text.strip(),
                "career_url": career_url,
                "company": "SoftProject GmbH",
            }) for item in items]}


@fetch_jobs
async def script_runner() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://scriptrunner.jobs.personio.de/"
        url = "https://scriptrunner.jobs.personio.de/search.json"
        async with session.get(url) as response:
            data = json.loads(await response.text())
            jobs: List[Job] = parse_personio(data, career_url, company='ScriptRunner Software GmbH')
            return {"script_runner": jobs}


@fetch_jobs
async def all_for_one() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://www.all-for-one.com/de/karriere/stellenangebote/?filterstate=%7B%22locations%22%3A%22Ettlingen%20bei%20Karlsruhe%22%7D"
        url = "https://api.all-for-one.com/query_de"
        payload = '''{
            offset:0,
            limit:999,
            query:"*",
            filter:[
                "website:allforonegroupag70794",
                "category:jobs",
                "locations:(\\"Ettlingen bei Karlsruhe\\")",
                "job_levels:(\\"Berufseinsteiger\\" || \\"Professionals\\")"
            ],
            fields:[
                url,title,locations,tstamp,job_levels
            ]
        }'''
        async with session.post(url, data=payload) as response:
            data = json.loads(await response.text())["response"]["docs"]
            return {"all_for_one": [Job(**{
                "title": d["title"],
                "url": d["url"],
                # "date": d["tstamp"],
                "seniority": d["job_levels"],
                "location": d["locations"],
                "career_url": career_url,
                "company": "All for One Group SE",
            }) for d in data]}


@fetch_jobs
async def raja_pack() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://karriere.rajapack.de/stellenangebote.html"
        url = "https://karriere.rajapack.de/stellenangebote.html"
        payload = 'reset_search=0&search_mode=job_filter_advanced&filter%5Bvolltext%5D=&filter%5Btaetigkeit_id%5D%5B%5D=3&filter%5Btaetigkeit_id%5D%5B%5D=4&filter%5Btaetigkeit_id%5D%5B%5D=5'

        async with session.post(url, data=payload) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
            container = soup.find('div', class_='real_table_container').div
            jobs = container.findAll('div', class_='joboffer_container')
            return {"raja_pack": [Job(**{
                "url": job.find('a')['href'],
                "title": job.find('a').text,
                "location": job.find('div', 'joboffer_informations').text.strip(),
                "career_url": career_url,
                "company": "Rajapack GmbH",
            }) for job in jobs]}


@fetch_jobs
async def netplans() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://www.netplans.de/karriere"
        url = "https://www.netplans.de/karriere"

        async with session.get(url) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
            jobboxes = soup.find('div', {'id': 'jobboxes'}).find('div', class_='newsflash')
            jobs = jobboxes.findAll('div', 'job-info')
            jobs = [job for job in jobs if "Ettlingen" in job.text]
            return {"netplans": [Job(**{
                "url": "https://netplans.de" + job.find('a')['href'],
                "title": job.find('a').text.strip() + " " + job.find('p', class_='job-gender').text.split("-")[
                    0].strip(),
                "location": [loc.strip() for loc in job.find('p', class_='job-gender').text.split("-")[1].split(',')],
                "career_url": career_url,
                "company": "NetPlans GmbH",
            }) for job in jobs]}


@fetch_jobs
async def ndt_global() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://ndt-global.onapply.de/"
        url = "https://ndt-global.onapply.de/board/xhr-get-filtered-forms.html?department=all&locality=Stutensee&country=DE"

        async with session.get(url) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
            departments = soup.findAll('div', class_='job-part')
            jobs = []
            for department in departments:
                department_jobs = department.findAll('div', 'jobs')
                for job in department_jobs:
                    location_span = job.find('h4').find('span')
                    location = location_span.text
                    location_span.extract()
                    jobs.append(Job(**{
                        "title": job.find('h4').text.strip(),
                        "url": job.find('a')['href'],
                        "location": location,
                        "career_url": career_url,
                        "department": department.find('div', 'dep-row').find('h3').text,
                        "company": "NDT Global GmbH & Co. KG",
                    }))

            return {"ndt_global": jobs}


@fetch_jobs
async def agilent() -> Dict[str, List[Dict[str, Any]]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://recruiting.adp.com/srccar/public/RTI.home?c=2167807"
        url = "https://recruiting.adp.com/srccar/public/rest/1/115407/search/"
        pages = [1, 2, 3, 4, 5, 6]
        await session.get(career_url)  # get the cookie, first
        jobs = []
        for page in pages:
            payload = '''{"filters":[
                {"name":"country","label":"Country"},
                {"name":"city","label":"Town/City"},
                {"name":"zzreqJobType","label":"Job Type"}
            ],"results":{
                "fields":[
                    {"name":"ptitle","label":"Published Job Title"},
                    {"name":"location","label":"Location"}
            ]},"pagefilter":{
                "country":["\\"DEU\\""],
                "page":''' + str(page) + ''',
                "city":["\\"Waldbronn\\""],
                "zzreqJobType":["\\"Experienced\\"","\\"Graduate\\""]},
            "rl":"enUS"}'''
            async with session.post(url, data=payload) as response:
                data = json.loads(await response.text())['jobs']
                jobs += [Job(**{
                    "url": d["url"],
                    "title": d["ptitle"],
                    "location": d["city"],
                    "career_url": career_url,
                    "company": "Agilent Technologies, Inc.",
                }) for d in data]
        return {"agilent": jobs}


@fetch_jobs
async def ntt_data() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://de.nttdata.com/Stellenangebote/page/1?location=Ettlingen"
        url = "https://de.nttdata.com/Stellenangebote/page/{}?location=Ettlingen"
        async with session.get(url.format(1)) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
            num_pages = nttData_get_num_pages(soup)

        # fetch jobs
        jobs: List[Job] = []
        for page in range(1, num_pages):
            async with session.get(url.format(page)) as response:
                soup = BeautifulSoup(await response.text(), 'html.parser')
                jobs += nttData_get_jobs(soup, career_url, company='NTT DATA Deutschland GmbH')

        return {"ntt_data": jobs}


@fetch_jobs
async def pneuhage() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        session.headers.update({'Content-Type': 'application/x-www-form-urlencoded'})
        career_url = "https://www.pneuhage.de/nc/unternehmen/jobs-und-karriere/stellenangebote/jobact/list"
        url = "https://www.pneuhage.de/nc/unternehmen/jobs-und-karriere/stellenangebote/jslocation/{}/jstaskarea/5/joborder/taskarea_desc/jobact/list"

        jobs: List[BeautifulSoup] = []
        locations = [18, 35]  # Ettlingen, Karlsruhe

        for location in locations:
            async with session.get(url.format(location)) as response:
                soup = BeautifulSoup(await response.text(), 'html.parser')
                jobtable = soup.find('table', {'id': 'jobtable'})
                if jobtable:
                    jobs += jobtable.findAll('tr', class_='joblistitem')

        result: List[Job] = []
        for job in jobs:
            title, location, department, schedule, _ = job.findAll('td')
            result.append(Job(**{
                "url": title.find('a')['href'],
                "title": title.text.strip(),
                "location": location.text.strip(),
                "department": department.text.strip(),
                "schedule": schedule.text.strip(),
                "career_url": career_url,
                "company": "Pneuhage Management GmbH & Co. KG",
            }))
        return {"pneuhage": result}


@fetch_jobs
async def rdb_wave() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://www.rbs-wave.de/jobmarkt/"
        url = "https://www.rbs-wave.de/wp-json/wp/v2/posts?categories=256&per_page=100"
        async with session.get(url) as response:
            jobs = json.loads(await response.text())
            return {"rdb_wave": [Job(**{
                "url": job["link"],
                "title": job["title"]["rendered"],
                "date": job["modified"],
                "location": job["excerpt"]["rendered"].split()[0].replace("<p>", "").replace("h4", "").strip(),
                "career_url": career_url,
                "company": "RBS wave GmbH",
            }) for job in jobs]}


@fetch_jobs
async def promatis() -> Dict[str, List[Job]]:
    session = requests.session()
    session.headers.update(headers)
    urls = ["https://www.promatis.de/en/jobs/young-professionals/", "https://www.promatis.de/en/jobs/professionals/"]
    jobs: List[Job] = []
    for url in urls:
        response = session.get(url, verify='certificates/promatis-de-zertifikatskette.pem')
        if response:
            soup = BeautifulSoup(response.text, 'html.parser')
            sections = soup.main.findAll('section', class_='color_footer-bottom')[1:]
            for section in sections:
                div = section.div
                department, title, location = div.findAll('div', class_='vc_column_container')
                jobs.append(Job(**{
                    "url": title.find('a')['href'],
                    "title": title.text.strip(),
                    "department": department.text.strip(),
                    "location": [loc.strip() for loc in location.text.split(",")],
                    "career_url": url,
                    "company": "PROMATIS software GmbH",
                }))
    return {"promatis": jobs}


@fetch_jobs
async def konica_minolta() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://www.konicaminolta.de/de-de/karriere/jobs"
        url = "https://www.konicaminolta.de/de-de/karriere/jobs"
        async with session.get(url) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
            jobs = soup.find('ul', class_='jobs-category__list').findAll('li')
            jobs = [job for job in jobs if "ettlingen" in job.text.lower()]
            return {"konica Minolta": [Job(**{
                "url": job.find('a')['href'],
                "title": job.find('h3').text.strip(),
                "location": [location.strip() for location in
                             job.find('p', class_='jobs-category__location').text.split(',')],
                "career_url": career_url,
                "company": "Konica Minolta Business Solutions Deutschland GmbH",
            }) for job in jobs]}


@fetch_jobs
async def flowserve() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = 'https://flowservecareers.com/ettlingen/none/deu/jobs/'
        url = 'https://flowservecareers.com/ettlingen/none/deu/jobs/'
        async with session.get(url) as response:
            if response:
                soup = BeautifulSoup(await response.text(), 'html.parser')
                jobs = soup.find('ul', class_='default_jobListing').findAll('li', 'direct_joblisting')
                return {"flowserve": [Job(**{
                    "url": "https://flowservecareers.com" + job.find('a')['href'],
                    "title": job.find('a').text.strip(),
                    "location": json.loads(job.find('span', 'hiringPlace')['data-job-posting'])['location'],
                    "department": json.loads(job.find('span', 'hiringPlace')['data-job-posting'])['job_category'],
                    "schedule": json.loads(job.find('span', 'hiringPlace')['data-job-posting'])['job_type'],
                    "career_url": career_url,
                    "company": "Flowserve Corporation",
                }) for job in jobs]}


@fetch_jobs
async def bruker() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        session.headers.update({'Referer': 'https://germancareers-bruker.icims.com/'})
        career_url = 'https://worldwidecareers-bruker.icims.com/jobs/search?pr=0&searchLocation=13183--'
        url = 'https://worldwidecareers-bruker.icims.com/jobs/search?pr={}&searchLocation=13183--&mobile=false&width=940&height=500&bga=true&needsRedirect=false&jan1offset=60&jun1offset=120&in_iframe=1'
        async with session.get(url.format(0)) as response:
            # collect job pages
            soup = BeautifulSoup(await response.text(), 'html.parser')
            pages = set([a['href'] for a in soup.find('div', 'iCIMS_PagingBatch').parent.findAll('a')])
            pages = set([page[:page.find("--")] for page in pages if "--" in page])

        if pages:
            jobs: List[Job] = []
            for page in pages:
                async with session.get(page) as response:
                    soup = BeautifulSoup(await response.text(), 'html.parser')
                    listings = soup.find('div', class_='iCIMS_JobsTable')
                    job_rows_all = listings.findAll('div', class_='row')
                    job_rows = [row for row in job_rows_all if
                                "ettlingen" in row.text.lower() or "remote" in row.text.lower()]
                    jobs += [Job(**{
                        "url": job.find('div', class_='title').find('a')['href'],
                        "title": job.find('div', class_='title').find('a').find('span', class_=None).text.strip(),
                        "location": [l.strip() for l in
                                     job.select('div.header.left')[0].find('span', class_=None).text.strip().split(
                                         "|")],
                        "date": job.select('div.header.right')[0].find('span', class_=None)['title'],
                        "career_url": career_url,
                        "company": "Bruker Corporation",
                    }) for job in job_rows]

            return {"bruker": jobs}


@fetch_jobs
async def sit() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://www.sit-de.com/de/karriere/offene-stellen/"
        url = "https://www.sit-de.com/de/karriere/offene-stellen/"
        async with session.get(url) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
            jobs = soup.findAll('div', 'job-pad')
            return {"sit": [Job(**{
                "url": "https://www.sit-de.com/de/karriere/offene-stellen/" + job.find('h1').find('a')['href'][2:],
                "title": job.find('h1').find('a').text,
                "career_url": career_url,
                "company": "Sit SteuerungsTechnik GmbH",
            }) for job in jobs]}


@fetch_jobs
async def otx_force() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://www.otx-force.de/karriere-bei-otx-force/"
        url = "https://www.otx-force.de/karriere-bei-otx-force/"
        async with session.get(url) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
            jobdiv = soup.find('div', {'id': 'offene-stellen'}).find('div', 'entry-content-wrapper')
            jobs = jobdiv.findAll('div', 'offenestelle')
            return {"otx_force": [Job(**{
                "url": "https://www.otx-force.de" + job.find('a')['href'],
                "title": job.find('h4').text,
                "date": job.find('p').text,
                "career_url": career_url,
                "company": "OTX Force GmbH",
            }) for job in jobs]}


@fetch_jobs
async def schleupen() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://www.schleupen.de/jobs-karriere/stellenangebote"
        url = "https://recruitingapp-5220.de.umantis.com/Jobs/1"
        async with session.get(url) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
            jobtable = soup.find('table', class_='tableaslist')
            jobs = jobtable.findAll('div', 'tableaslist_cell')
            results = []
            for job in jobs:
                a, schedule, type_, department, location, keywords, _, _ = job.findAll('span')
                results.append(Job(**{
                    "url": "https://recruitingapp-5220.de.umantis.com" + a.find('a')['href'],
                    "title": a.find('a').text.strip(),
                    "location": location.text[location.text.find(":") + 1:].replace("|", "").strip(),
                    "schedule": schedule.text[schedule.text.find(":") + 1:].replace("|", "").strip(),
                    "department": department.text[department.text.find(":") + 1:].replace("|", "").strip(),
                    "keywords": keywords.text[keywords.text.find(":") + 1:].replace("|", "").strip(),
                    "career_url": career_url,
                    "company": "Schleupen AG",
                }))

            return {"schleupen": results}


@fetch_jobs
async def liebherr() -> Dict[str, List[Job]]:
    session = requests.session()
    session.headers.update(headers)
    career_url = "https://www.liebherr.com/en/int/career/job-vacancies/job-vacancies.html?postingCountry=DE&entrylevel=35031&company=34385&size=50"
    url = "https://www.liebherr.com/en/int/career/job-vacancies/job-vacancies.html?postingCountry=DE&entrylevel=35031&company=34385&size=50"
    response = session.get(url, verify='certificates/liebherr-com-zertifikatskette.pem')
    if response:
        soup = BeautifulSoup(response.text, 'html.parser')
        jobs = soup.find('ol', class_='mysuccess-results_list').findAll('li', class_='mysuccess-results_list-item')
        return {'liebherr': [Job(**{
            'url': 'https://www.liebherr.com' + job.find('a')['href'],
            'title': job.find('h2').text,
            'location': [loc.strip() for loc in
                         job.find('p', class_='mysuccess-results_standfirst').text.split(',')[0]],
            'keywords': [key.strip() for key in
                         job.find('p', class_='mysuccess-results_standfirst').text.split(',')[1].split('/')],
            'career_url': career_url,
            'company': 'Liebherr-International Deutschland GmbH',
        }) for job in jobs]}


@fetch_jobs
async def dachser() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        session.headers.update({'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'})
        career_url = "https://de.dachser-career.com/job-finden?category=All&entry_level=All&location=113"
        url = "https://de.dachser-career.com/views/ajax?hide_exposed_form=1"
        payload = 'view_name=jobs&view_display_id=default&location=113&page={}'
        jobs: List[Job] = []
        for page in [0, 1, 2]:
            async with session.post(url.format(page), data=payload) as response:
                data = json.loads(await response.text())[-1]['data']
                soup = BeautifulSoup(data, 'html.parser')
                job_items: List[BeautifulSoup] = soup.findAll('div', 'job-item')
                jobs += [Job(**{
                    'url': 'https://de.dachser-career.com' + job.find('a')['href'],
                    'title': job.find('div', class_='job-title').text.strip(),
                    'location': job.find('div', class_='job-city').text.strip(),
                    'career_url': career_url,
                    'company': 'DACHSER SE',
                }) for job in job_items]
        result: List[Job] = []
        for job in jobs:
            if job not in result:
                result.append(job)
        return {'dachser': result}


@fetch_jobs
async def daimer_tss() -> Dict[str, List[Job]]:
    session = requests.session()
    session.headers.update(headers)
    career_url = "https://www.daimler-tss.com/de/karriere/jobs/#berufserfahrene_absolventen"
    url = "https://www.daimler-tss.com/de/karriere/jobs/#berufserfahrene_absolventen"
    response = session.get(url, verify='certificates/daimler-tss-de-zertifikatskette.pem')
    if response:
        soup = BeautifulSoup(response.text, 'html.parser')
        job_table = soup.find('div', {'id': 'berufserfahrene_absolventen'}).table.tbody
        jobs: List[BeautifulSoup] = job_table.findAll('tr')
        return {'daimler_tss': [Job(**{
            'url': 'https://www.daimler-tss.com/de/karriere/jobs/' + job.find('a')['href'],
            'title': job.find('a').text.strip(),
            'location': [location.strip() for location in job.findAll('td')[1].text.split(',')],
            'career_url': career_url,
            'company': 'Daimler TSS GmbH',
        }) for job in jobs]}


@fetch_jobs
async def stp() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://www.stp-online.de/aktuelle-stellenangebote/"
        url = "https://stp-online.softgarden.io/de/widgets/jobs"
        async with session.get(url) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
            jobs: List[BeautifulSoup] = soup.find('div', class_='outputContainer').findAll('div', class_='matchElement')
            return {'stp': [Job(**{
                'url': 'https://stp-online.softgarden.io' + job.find('a')['href'][5:],
                'title': job.find('a').text,
                'date': job.find('div', class_='date').text,
                'department': job.find('div', class_='jobcategory').text,
                'location': job.find('div', class_='ProjectGeoLocationCity').text,
                'career_url': career_url,
                'company': 'STP Informationstechnologie GmbH',
            }) for job in jobs]}


@fetch_jobs
async def cynora() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://cynora.com/de/karriere/aktuelle-stellenangebote/professionals/"
        url = "https://cynora.com/de/karriere/aktuelle-stellenangebote/professionals/"
        async with session.get(url) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
            jobs: List[BeautifulSoup] = soup.findAll('div', class_='rowJobs')
            return {'cynora': [Job(**{
                'url': job.find('a')['href'],
                'title': job.find('a').text[job.find('a').text.find('–') + 1:].strip(),
                'career_url': career_url,
                'company': 'cynora GmbH',
            }) for job in jobs]}


@fetch_jobs
async def netze_bw() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://careers.netze-bw.de/de_DE/netzebw/SearchJobs/?452=%5B377%2C4577242%2C208385%2C380%5D&452_format=676&499=%5B571%2C575%5D&499_format=797"
        url = "https://careers.netze-bw.de/de_DE/netzebw/SearchJobs/?452=%5B377%2C4577242%2C208385%2C380%5D&452_format=676&499=%5B571%2C575%5D&499_format=797"
        async with session.get(url) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
            jobs: List[BeautifulSoup] = soup.find('ul', class_='list--jobs').findAll('li')
            return {'netze_bw': [Job(**{
                'url': job.find('div', 'list__item__text').find('a')['href'],
                'title': job.find('div', 'list__item__text').find('a').text.strip(),
                'date': job.find('div', 'list__item__text__subtitle').text[
                        job.find('div', 'list__item__text__subtitle').text.find(' '):
                        job.find('div', 'list__item__text__subtitle').text.find(',')].strip(),
                'location': job.find('div', 'list__item__text__subtitle').text[
                            job.find('div', 'list__item__text__subtitle').text.find(',') + 1:].strip(),
                'career_url': career_url,
                'company': 'Netze BW GmbH',
            }) for job in jobs]}


@fetch_jobs
async def fiducia_gad() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://fiduciagad-karriereportal.mein-check-in.de/list?keywords=&extensions[status][0]=executive&extensions[status][1]=professional&location_names[0]=Karlsruhe%2C+Baden-Württemberg"
        url = "https://fiduciagad-karriereportal.mein-check-in.de/list?keywords=&extensions[status][0]=executive&extensions[status][1]=professional&location_names[0]=Karlsruhe%2C+Baden-Württemberg&page=1"
        jobs_results: List[Job] = []
        while True:
            async with session.get(url) as response:
                soup = BeautifulSoup(await response.text(), 'html.parser')
                jobs: List[BeautifulSoup] = soup.findAll('div', class_='result')
                jobs_results += [Job(**{
                    'url': 'https://fiduciagad-karriereportal.mein-check-in.de' + job.find('h3').find('a')['href'],
                    'title': job.find('h3').text.split(' ', maxsplit=1)[1].split('|')[0].strip(),
                    'date': job.find('span', class_='date').text,
                    'location': job.find('span', class_='location').text,
                    'career_url': career_url,
                    'company': 'Fiducia & GAD IT AG',
                }) for job in jobs]
                next_url = soup.find('div', class_='pagination-wrapper').find('a', class_='next')
                if next_url:
                    url = "https://fiduciagad-karriereportal.mein-check-in.de" + next_url['href']
                else:
                    break
        return {'fiducia_gad': jobs_results}


@fetch_jobs
async def ptv() -> Dict[str, List[Job]]:
    career_url = "https://stellenangebote.ptvgroup.com/job-offers.html"
    url = "https://stellenangebote.ptvgroup.com/job-offers.html"
    payload = "&filter%5Bcountr%5D%5BDE%2C+Karlsruhe%5D=DE%2C+Karlsruhe&filter%5Btaetigkeit_id%5D%5B4%5D=4"
    return {'ptv': await parse_rexx(url, payload, career_url, company='PTV Planung Transport Verkehr AG')}


@fetch_jobs
async def nesto() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://nesto-software.de/jobs/"
        url = "https://nesto-software.de/jobs/"
        async with session.get(url) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
            job_section = soup.find('div', {'id': 'career'}).find('div', class_='feature_list').find('ul')
            jobs = [li.find('a') for li in job_section.findAll('li')]
            return {'nesto': [Job(**{
                'url': job['href'],
                'title': job.text,
                'career_url': career_url,
                'company': 'Nesto Software GmbH',
            }) for job in jobs]}


@fetch_jobs
async def blue_yonder() -> Dict[str, List[Job]]:
    career_url = 'https://jda.wd5.myworkdayjobs.com/JDA_Careers/2/refreshFacet/318c8bb6f553100021d223d9780d30be'
    url = 'https://jda.wd5.myworkdayjobs.com/JDA_Careers/'
    payload = 'facets=locations,workerSubType&locations=locations::587c171d971b01a30a44927aaeb9d649&workerSubType=workerSubType::6a96b8f1ac9e1043fb5c6777e6718c89'
    jobs = await parse_workday(url, payload, career_url, 'Blue Yonder Group, Inc.')
    for job in jobs:
        job.location = 'Karlsruhe'
    return {'blue_yonder': jobs}


@fetch_jobs
async def kone() -> Dict[str, List[Job]]:
    career_url = 'https://kone.wd3.myworkdayjobs.com/Careers/7/refreshFacet/318c8bb6f553100021d223d9780d30be'
    url = 'https://kone.wd3.myworkdayjobs.com/Careers/'
    payload = 'facets=locations&locations=locations::c44b225df5b901cdad925c27c614121f'
    jobs = await parse_workday(url, payload, career_url, 'KONE GmbH')
    for job in jobs:
        job.location = 'Ettlingen'
    return {'kone': jobs}


@fetch_jobs
async def sovendus() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        session.headers.update({'Content-Type': 'application/x-www-form-urlencoded', })
        career_url = 'https://online.sovendus.com/karriere/stellenangebote/'
        url = 'https://sovendus.jobbase.io/'
        payload = 'candidate_center_filter%5Bcity%5D=140180&candidate_center_filter%5BhasCityCluster%5D=1&candidate_center_filter%5Bdistance%5D=20'
        async with session.post(url, data=payload) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
            job_divs: List[BeautifulSoup] = soup.findAll('div', 'row-table-condensed')
            jobs: List[Job] = []
            for job in job_divs:
                link, location, type_, date_ = job.findAll('div', 'cell-table')
                if type_ != "Praktikum":
                    jobs.append(Job(**{
                        'url': 'https://sovendus.jobbase.io/' + link.find('a')['href'],
                        'title': link.find('a').text.strip(),
                        'schedule': type_.text.strip(),
                        'date': date_.text.strip(),
                        'location': location.text.strip(),
                        'career_url': career_url,
                        'company': 'Sovendus GmbH',
                    }))

            return {'sovendus': jobs}


@fetch_jobs
async def siemens() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://jobs.siemens.com/jobs?page=1&locations=Karlsruhe,Baden-W%C3%BCrttemberg,Deutschland%7CKarlsruhe,Baden-W%C3%BCrttemberg,Germany&experienceLevels=Early%20Professional%7CExperienced%20Professional%7CGraduate%7CProfessional"
        url = "https://jobs.siemens.com/api/jobs?page={}&locations=Karlsruhe%2CBaden-W%C3%BCrttemberg%2CDeutschland|Karlsruhe%2CBaden-W%C3%BCrttemberg%2CGermany&experienceLevels=Early%20Professional|Experienced%20Professional|Graduate|Professional"
        jobs: List[Job] = []
        page = 1
        while True:
            async with session.get(url.format(page)) as r:
                response = json.loads(await r.text())
                data = [job['data'] for job in response['jobs']]
                total_count = response['totalCount']
                jobs += [Job(**{
                    'url': d['meta_data']['canonical_url'],
                    'title': d['title'],
                    'location': d['city'],
                    'department': [category['name'] for category in d['categories']],
                    'seniority': d['experience_levels'],
                    'schedule': d['meta_data']['job_type'],
                    'date': d['update_date'],
                    'career_url': career_url,
                    'company': 'Siemens ' + d['brand'].replace('Siemens', '').strip(),
                }) for d in data]
            if total_count - (page * 10) < 0:
                break
            else:
                page += 1
        return {'siemens': jobs}


@fetch_jobs
async def baker_hughes() -> Dict[str, List[Job]]:
    url = 'https://bakerhughes.wd5.myworkdayjobs.com/BakerHughes/'
    career_url = "https://careers.bakerhughes.com/global/en/search-results?qcity=Stutensee&qcountry=Germany&qstate=Baden-Wurttemberg&location=Stutensee,%20Baden-Wurttemberg,%20Germany"
    payload = 'facets=locationHierarchy%2ClocationHierarchy2&locationHierarchy=locationHierarchy::5ec015e564230118207a74645e508e2c&locationHierarchy2=locationHierarchy2::5ec015e5642301e2e84b31665e50db39&sessionSecureToken=7n49t8ifklgsms85h65q2bavnr&clientRequestID=0f1aa18cf16f400f88bab45511fdd2f9'
    jobs = await parse_workday(url, payload, career_url, 'Baker Hughes Company')
    for job in jobs:
        job.location = 'Stutensee'
    return {'baker_hughes': jobs}


@fetch_jobs
async def top_itservices() -> Dict[str, List[Job]]:
    career_url = "https://www.top-itservices.com/ueber-uns/interne-karriere/offene-stellen"
    url = "https://www.top-itservices.com/ueber-uns/interne-karriere/offene-stellen"
    response = requests.get(url)
    if response:
        soup = BeautifulSoup(response.text, 'html.parser')
        karlsruhe = soup.find('div', {'id': 'Karlsruhe'})
        if karlsruhe:
            jobs: List[BeautifulSoup] = karlsruhe.findNext('ul').findAll('li')
        else:
            jobs = []
        return {'top_itservices': [Job(**{
            'url': 'https://www.top-itservices.com' + job.find('a')['href'],
            'title': job.find('a').text.strip(),
            'career_url': career_url,
            'company': 'top itservices AG',
        }) for job in jobs]}


@fetch_jobs
async def usu() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://www.usu.com/de-de/unternehmen/karriere/jobs/?city=Karlsruhe"
        url = "https://www.usu.com/de-de/unternehmen/karriere/jobs/?city=Karlsruhe"
        async with session.get(url) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
            job_list = soup.find('div', class_='listing__main')
            jobs: List[BeautifulSoup] = [job.find('section', class_='row') for job in
                                         job_list.findAll('div', class_='listing__item')]
            return {'usu': [Job(**{
                'url': 'https://www.usu.com' + job.find('h3').find('a')['href'],
                'title': job.find('h3').find('a').text.strip(),
                'location': [location.strip() for location in
                             job.find('dl', class_='row__fact-2').find('dd', class_='row__fact-value').text.split(',')],
                'seniority': job.find('span').text.strip(),
                'department': job.find('dl', class_='row__fact-1').find('dd', class_='row__fact-value').text.strip(),
                'career_url': career_url,
                'company': 'USU Software AG',
            }) for job in jobs]}


@fetch_jobs
async def andrena() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = "https://www.andrena.de/berufserfahrene"
        url = "https://www.andrena.de/berufserfahrene"
        async with session.get(url) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
            job_list = soup.find('div', class_='angebote-wrapper')
            job_list.find('div', class_='studierende').decompose()
            jobs: List[BeautifulSoup] = [li.a for li in job_list.findAll('li')]
            return {'andrena': [Job(**{
                'url': job['href'],
                'title': job.text.strip(),
                'career_url': career_url,
                'company': 'andrena objects ag',
            }) for job in jobs]}


@fetch_jobs
async def funkinform() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        career_url = "https://www.funkinform.digital/karriere/"
        url = "https://www.funkinform.digital/karriere/"
        async with session.get(url) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
            jobs: List[BeautifulSoup] = [div.h4.a for div in soup.findAll('div', 'job-box')]
            return {'funkinform': [Job(**{
                'url': 'https://www.funkinform.digital' + job['href'],
                'title': job.text.strip(),
                'career_url': career_url,
                'company': 'Funkinform Informations- und Datentechnik GmbH',
            }) for job in jobs]}


@fetch_jobs
async def ferchau() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(headers)
        career_url = 'https://www.ferchau.com/de/de/bewerber/jobs'
        urls = [
            'https://api.ferchau.com/v4/recruiting/search?hyphen=override&lang=1,2&count=ferchau&limit=250&offset=0&type=3&lat=48.93333&lon=8.4&radius=10&target=5',
            'https://api.ferchau.com/v4/recruiting/search?hyphen=override&lang=1,2&count=ferchau&limit=250&offset=0&type=3&lat=48.93333&lon=8.4&radius=10&target=12']

        jobs: List[Job] = []
        for url in urls:
            async with session.get(url) as response:
                jobs_result: List[Dict] = json.loads(await response.text())['matches']
                jobs += [Job(**{
                    'url': f"https://www.ferchau.com/de/de/bewerber/jobs/{job['njobid']}",
                    'title': job['sjobbez'],
                    'location': job['seinsatzort'],
                    'date': job['dtvon'],
                    'company': job['sorganisationbez'] + ',' + job['sniederlassungbez'],
                    'keywords': job.get('sstichwoerter', ''),
                    'career_url': career_url,
                }) for job in jobs_result]
        result: List[Job] = []
        for job in jobs:
            if job not in result:
                result.append(job)

        return {'ferchau': result}


@fetch_jobs
async def eins_und_eins() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update({
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        })

        career_url = 'https://jobs.1und1.de'
        await session.get(career_url)  # get cookies

        seniority = {'graduates': 'Junior', 'professionals': 'Senior'}
        payload = 'tx_cisocareer_jobsearchform%5B__trustedProperties%5D=a%3A6%3A%7Bs%3A10%3A%22textSearch%22%3Bi%3A1%3Bs%3A11%3A%22careerLevel%22%3Ba%3A1%3A%7Bi%3A0%3Bi%3A1%3B%7Ds%3A10%3A%22categories%22%3Ba%3A1%3A%7Bi%3A0%3Bi%3A1%3B%7Ds%3A12%3A%22locationName%22%3Ba%3A1%3A%7Bi%3A0%3Bi%3A1%3B%7Ds%3A11%3A%22companyName%22%3Ba%3A1%3A%7Bi%3A0%3Bi%3A1%3B%7Ds%3A11%3A%22referenceId%22%3Bi%3A1%3B%7Dcf9e75a0390e69dc8f2a854a9aeae644372dc475&tx_cisocareer_jobsearchform%5BcareerLevel%5D%5B%5D={}&tx_cisocareer_jobsearchform%5BlocationName%5D%5B%5D=Karlsruhe'

        jobs: List[Job] = []
        for seniority_, seniority_value in seniority.items():
            async with session.post(career_url, data=payload.format(seniority_)) as response:
                soup = BeautifulSoup(await response.text(), 'html.parser')
                links = [career_url + a['href'] for a in
                         soup.find('div', 'main-content').findAll('a', 'category-label')]
                for link in links:
                    async with session.get(link) as sub_site:
                        soup = BeautifulSoup(await sub_site.text(), 'html.parser')
                        offers: List[BeautifulSoup] = soup.find('div', 'main-content').find('ul',
                                                                                            'joboffer-result-list').findAll(
                            'li',
                            'clearfix')
                        jobs += [Job(**{
                            'url': career_url + job.a['href'],
                            'title': job.a.text.strip(),
                            'location': 'Karlsruhe',
                            'department': soup.find('div', 'main-content').h1.text.replace('Jobangebote', '').strip(),
                            'career_url': career_url,
                            'company': job.find('br').next.strip()[4:job.find('br').next.strip().find(' in ')],
                            'seniority': seniority_value,
                        }) for job in offers]

        return {'1&1': jobs}


@fetch_jobs
async def pace_car() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        career_url = "https://www.pace.car/en/jobs"
        url = "https://www.pace.car/en/jobs"
        async with session.get(url) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
            jobs: List[BeautifulSoup] = soup.find('div', 'jobs-table').tbody.findAll('tr')
            return {'pace.car': [Job(**{
                'url': 'https://www.pace.car' + job.find('tr', class_='job-link').a['href'],
                'title': job.find('tr', class_='job-title').text.strip(),
                'location': job.find('tr', class_='job-location').text.strip(),
                'schedule': job.find('tr', class_='job-hours').text.strip(),
                'career_url': career_url,
                'company': 'PACE Telematics GmbH',
            }) for job in jobs]}


@fetch_jobs
async def log_me_in() -> Dict[str, List[Job]]:
    url = 'https://logmein.wd5.myworkdayjobs.com/LogMeInCareers/'
    career_url = "https://logmein.wd5.myworkdayjobs.com/LogMeInCareers/4/refreshFacet/318c8bb6f553100021d223d9780d30be"
    payload = 'state=%3Cwml%3AFaceted_Search_State+Enable_Save%3D%221%22+xmlns%3Awul%3D%22http%3A%2F%2Fwww.workday.com%2Fns%2Fuser-interface%2F1.0%22+xmlns%3Awd%3D%22urn%3Acom.workday%2Fbsvc%22+xmlns%3Anyw%3D%22urn%3Acom.netyourwork%2Faod%22+xmlns%3Awml%3D%22http%3A%2F%2Fwww.workday.com%2Fns%2Fmodel%2F1.0%22%3E%3Cwml%3ARequest%3E%3Cwd%3AReport_Parms_Selection%3E%3Cwd%3AReport_Definition__All_--IS%3E%3Cnyw%3ARI+IID%3D%22undefined%22%2F%3E%3C%2Fwd%3AReport_Definition__All_--IS%3E%3Cwd%3AReport_Parms%2F%3E%3Cnyw%3AFaceted_Query_Request%3E%3Cnyw%3AFaceted_Query_Request_Selection%3E%3Cnyw%3ASelected_Facet--IS%3E%3Cnyw%3ARI+IID%3D%22locations%22%2F%3E%3C%2Fnyw%3ASelected_Facet--IS%3E%3Cnyw%3ASelected_Facet_Values--IS%3E%3Cnyw%3ARI+IID%3D%22locations::593d854cb26f01137b17320c00025e23%22%2F%3E%3Cnyw%3ARI+IID%3D%22locations::593d854cb26f018a95dde40d00023c24%22%2F%3E%3C%2Fnyw%3ASelected_Facet_Values--IS%3E%3C%2Fnyw%3AFaceted_Query_Request_Selection%3E%3Cnyw%3AFaceted_Query_Request_Selection%3E%3Cnyw%3ASelected_Facet--IS%3E%3Cnyw%3ARI+IID%3D%22workerSubType%22%2F%3E%3C%2Fnyw%3ASelected_Facet--IS%3E%3Cnyw%3ASelected_Facet_Values--IS%3E%3Cnyw%3ARI+IID%3D%22workerSubType::14a2d0b6b3611078126725c3039da755%22%2F%3E%3C%2Fnyw%3ASelected_Facet_Values--IS%3E%3C%2Fnyw%3AFaceted_Query_Request_Selection%3E%3C%2Fnyw%3AFaceted_Query_Request%3E%3C%2Fwd%3AReport_Parms_Selection%3E%3C%2Fwml%3ARequest%3E%3Cwml%3AFacet_Configuration%3E%3Cwml%3AFacet_Expand_State%3E%3Cwml%3AFacet+Expand%3D%22full%22+IID%3D%22locations%22%2F%3E%3Cwml%3AFacet+Expand%3D%22full%22+IID%3D%22workerSubType%22%2F%3E%3Cwml%3AFacet+Expand%3D%22half%22+IID%3D%22timeType%22%2F%3E%3C%2Fwml%3AFacet_Expand_State%3E%3C%2Fwml%3AFacet_Configuration%3E%3C%2Fwml%3AFaceted_Search_State%3E'
    jobs = await parse_workday(url, payload, career_url, 'LogMeIn Ireland Unlimited Company')
    for job in jobs:
        job.location = 'Karlsruhe'
    return {'logMeIn': jobs}


@fetch_jobs
async def dm() -> Dict[str, List[Job]]:
    async with aiohttp.ClientSession() as session:
        session.headers.update(
            {'api-key': '8DE66DF51831A58E3317536F02E737BB', 'Content-Type': 'application/json;charset=UTF-8'})
        career_url = 'https://www.dm-jobs.com/Germany/?locale=de_DE'
        url = 'https://csbep.search.windows.net/indexes/dm-prod/docs/search?api-version=2019-05-06'
        payload = "{\"count\":true,\"facets\":[],\"filter\":\"(search.ismatch('Karlsruhe') or search.ismatch('Ettlingen')) and jobType ne 'Ausbildung' and not search.ismatch('Werkstudent', 'title') and jobType ne 'Praktikum'\",\"search\":\"*\",\"skip\":0,\"top\":9999}"
        async with session.post(url, data=payload) as response:
            jobs = json.loads(await response.text())
            jobs = json.loads(await response.text())['value']

        return {'dm': [Job(**{
            'title': job['title'],
            'date': job['datePosted'],
            'url': job['link'],
            'company': f"dm ({job['brand']})",
            'schedule': job['workHours'],
            'department': job['department'],
            'location': job['filter2'],
            'career_url': career_url,
            'type_': job['jobType'],
        }) for job in jobs]}

# Backlog
# * https://www.kenbun.de/karriere/
