from pydantic import BaseModel, Field
from typing import List, Optional

class Cost(BaseModel):
    """
    A model to represent the low, mid, and upper cost estimates in dollars.
    """
    low: Optional[int] = None
    mid: Optional[int] = None
    upper: Optional[int] = None

class Team(BaseModel):
    """
    A model to represent the details for each team involved in a capability.
    """
    name: str = Field(..., alias='Team')
    estimation_contact: Optional[str] = Field(None, alias='Estimation Contact')
    ba_qa_support: Optional[str] = Field(None, alias='BA & QA Support')
    cost: Cost = Field(..., alias='Cost Information')

class Capability(BaseModel):
    """
    A model to represent a single capability, including all associated teams and cost totals.
    """
    capability: str
    teams: List[Team] = Field(..., alias='Team')
    sub_total: Cost = Field(..., alias='Sub Total')
    project_support: Cost = Field(..., alias='Project Support')
    total: Cost = Field(..., alias='Total')

class ProjectTShirt(BaseModel):
    """
    The main model to hold a list of all capabilities.
    """
    capabilities: List[Capability]

-----------------------------------------------------------------------------------------------
I have a contingency table in sheet called: "Project T-shirt"
In the table, it has column name as capability , OLBB CUA , OLBB - HP,RPT, etc along with sub total, project support , total. 
These olbb CUA is the team it has Estimation contact and BA & QA Support and low, mid, upper values. Each row has different capabilities mentioned with its
low, mid,upper value is dynamic .
You need to create a json schema to parse this information you can use pydantic for this.

schema = {  "capability": capability,
            "Team": like: olbb cua, olbb-hp, rpt, Digital core etc are to be stored in team key
            "Estimation Contact": estimation contact,
            "BA & QA Support": information,
            "Cost Information": low, mid, upper. This cost information as in dollars.
	    "Sub Total": low, mid, upper
	    "Project Support": low, mid, upper
	    "Total": low, mid, upper
        }
Here each capability is handled by either a single team or multiple teams. Hence it needs to create a json schema based on capability.
Sharing the image having this information for better response.
