{
  "initiative": {
    "title": "Mutual Funds in OLBB",
    "overview": {
      "objective": "Extend OLBB Homepage to support mutual fund accounts with product info, balances, holdings (name, price, units, market value, book value), and transaction history.",
      "TPS_intake_number": 3473,
      "sizing_level": "T-Shirt"
    }
  },
  "accountable_roles": {
    "LTO": "Santhosh Kumar Krishnamurthy",
    "STO": "Chunyuan Wang",
    "BC": "Charmaine Jackson",
    "SA": "Ashish Sinha"
  },
  "capabilities": [
    {
      "id": 1,
      "name": "Mutual Funds Product Selection",
      "components": {
        "LiveLink": {
          "support_contact": "BA & QA Support",
          "estimation_contact": "LiveLink Architects",
          "effort": { "low": null, "mid": null, "high": null }
        },
        "OLBB_CUA": {
          "support_contact": "BA & QA Included",
          "estimation_contact": "CUA Development Lead",
          "effort": { "low": null, "mid": null, "high": null }
        },
        "OLBB_HP_RPT": {
          "support_contact": "Aytan Javadova",
          "estimation_contact": "Reporting Team",
          "effort": { "low": null, "mid": null, "high": null }
        },
        "OLBB_PYMT": {
          "support_contact": "Mobile Payments Team",
          "estimation_contact": "Payments Architect",
          "effort": { "low": null, "mid": null, "high": null }
        },
        "IDP": {
          "support_contact": "BA & QA Support",
          "estimation_contact": "Integration Dev Lead",
          "effort": { "low": null, "mid": null, "high": null }
        }
      }
    },
    {
      "id": 2,
      "name": "Entitlement via Onboarding",
      "components": {
        "OLBB_CUA": {
          "support_contact": "BA & QA Included",
          "estimation_contact": "CUA Development Lead",
          "effort": { "low": null, "mid": 50, "high": 100 }
        }
      }
    },
    {
      "id": 3,
      "name": "Entitlement via OLBB CUA",
      "components": {
        "OLBB_CUA": {
          "support_contact": "BA & QA Included",
          "estimation_contact": "CUA Development Lead",
          "effort": { "low": null, "mid": 100, "high": 150 }
        }
      }
    },
    {
      "id": 4,
      "name": "Foundational Components to Update Homepage",
      "components": {
        "OLBB_CUA": {
          "support_contact": "BA & QA Included",
          "estimation_contact": "CUA Development Lead",
          "effort": { "low": null, "mid": 100, "high": 150 }
        },
        "OLBB_HP_RPT": {
          "support_contact": "Aytan Javadova",
          "estimation_contact": "Reporting Team",
          "effort": { "low": null, "mid": 100, "high": 125 }
        }
      }
    },
    {
      "id": 5,
      "name": "Homepage Extension for Mutual Funds",
      "components": {
        "OLBB_CUA": {
          "support_contact": "BA & QA Included",
          "estimation_contact": "CUA Development Lead",
          "effort": { "low": null, "mid": 150, "high": 200 }
        }
      }
    }
  ]
}

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
