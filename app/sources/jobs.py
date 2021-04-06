import datetime
import re
from dataclasses import dataclass
from typing import Union, List, Optional


@dataclass
class Job:
    title: str
    company: str
    career_url: str
    url: str
    location: Union[str, List] = ''
    date: Union[str, datetime.date] = datetime.date.today()
    keywords: Union[str, List] = ''
    department: str = ''
    schedule: str = ''
    seniority: Union[str, List[str]] = ''
    type_: Optional[str] = ''

    def __post_init__(self):
        if self.seniority == '':
            seniority = re.findall(r"(Senior)|(senior)|(Junior)|(junior)|(Expert[e|in]*)|(Erfahrene[r]*)", self.title)
            if seniority:
                self.seniority = [s for s in seniority[0] if s]

        if isinstance(self.location, str):
            self.location = [self.location]
