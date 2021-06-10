import datetime
import re
from dataclasses import dataclass, field
from typing import Union, List


@dataclass
class Job:
    title: str
    company: str
    career_url: str
    url: str
    location: Union[str, List[str]] = field(default_factory=list)
    date: Union[str, datetime.date] = field(default=datetime.date.today(), compare=False)
    keywords: Union[str, List[str]] = field(default_factory=list)
    department: str = ''
    schedule: str = ''
    seniority: Union[str, List[str]] = ''
    type_: str = ''

    def __post_init__(self):
        if self.seniority == '':
            seniority = re.findall(r"(Senior)|(senior)|(Junior)|(junior)|(Expert[e|in]*)|(Erfahrene[r]*)", self.title)
            if seniority:
                self.seniority = [s for s in seniority[0] if s]

        if isinstance(self.location, str):
            self.location = [self.location]
