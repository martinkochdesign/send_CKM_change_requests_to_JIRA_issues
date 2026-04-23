# CKM Change Requests to Jira issue Updater
> Script version: `0.2.0`

Updates openEHR CKM Change Requests (CRs) from `https://ckm.openehr.org` with Jira issues in the `CLINICAL` project on `https://openehr.atlassian.net`.
- Creates Jira parent issues for CKM archetypes and templates when missing.
- Creates Jira issues for CKM Change Requests if they do not yet exist.
- Updates existing Jira issues when CKM CRs change.
- Moves Jira issues to “In Progress” when corresponding CKM CRs move to `in-process`.
- Adds comments to Jira issues when CKM CRs are closed or missing from CKM.
- Logs all actions to a rotating log file.
---
## Overview
This script keeps Jira issues in sync with CKM Change Requests:
- Targets CKM API: `https://ckm.openehr.org/ckm/rest/v1/change-requests`
- Targets Jira project/board: `CLINICAL` at `https://openehr.atlassian.net`
- Uses Jira Automation webhooks to:
  - Create parent **Archetype** issues
  - Create parent **Template** issues
  - Create **CKM Change Request** issues
  - Update existing CR issues
  - Move issues to **In Progress** when CKM CR are `in-process`
  - Add comments when CRs are **closed** in CKM
  - Add comments when CRs are **missing** in CKM
All side‑effects in Jira are guarded by the `READWRITE` flag for safe dry‑runs.
---
## Prerequisites
- Python 3.8+ recommended
- Access to:
  - CKM: `https://ckm.openehr.org`
  - Jira Cloud: `https://openehr.atlassian.net`
- A Jira user with permissions to:
  - Read issues in project `CLINICAL`
  - Trigger Automation webhooks that create/update/transition issues
- Jira Automation rules and corresponding webhook URLs/tokens are configured in the corresponding GitHub secrets and laoded in the GitHub wokflow.
---
## Configuration
### Environment variables
#### Jira
The base URL for the JIRA queries is 
>JIRA_URL = "https://openehr.atlassian.net"

To query single issues from Jira the following URL is used:
>API_ENDPOINT = f"{JIRA_URL}/rest/api/2/issue"

To query the list of all issues, a JQL query is used, durected at the following URL:
>SEARCH_ENDPOINT = f"{JIRA_URL}/rest/api/3/search/jql"

7 different Jira automations are used to create or change Jira issues. Each needs their own URL and TOKEN:
- CKM_CR_to_JIRA_01_Create_Archetype_URL/TOKEN
- CKM_CR_to_JIRA_02_Create_Template_URL/TOKEN
- CKM_CR_to_JIRA_03_Create_CR_URL/TOKEN
- CKM_CR_to_JIRA_04_Update_CR_URL/TOKEN
- CKM_CR_to_JIRA_05_Move_to_In_Progress_URL/TOKEN
- CKM_CR_to_JIRA_06_Add_close_comment_URL/TOKEN
- CKM_CR_to_JIRA_07_Add_missing_comment_URL/TOKEN

#### CKM
The list of change requests in the CKM is accesed via the REST API:
>https://ckm.openehr.org/ckm/rest/v1/change-requests

This works for CKM versions 1.21.0 or higher.

### Read-only vs read-write mode
The script uses a global switch to permit execution without changes in the Jira Board:

>READWRITE = False  # default: dry-run

If `READWRITE` is `False`, only information is read from Jira and CKM. 

> [!NOTE]  
> The log will show that changes has been made, but these are just simulated changes. No Jira changes are performed.

If `READWRITE` is `True`, Jira Automation webhooks are called. Issues, comments and transitions are actually applied.

---
### Local vs non-local mode

A flag is implemented for local use of the script. In development the `LOCAL` flag can be set to `True` and the values for the credentials can be added to the `if...then` statement.
You must adjust the code if you want to provide credentials differently (e.g., hard‑coding or from a config file).

In the published version, any hardcoded credentials have to be deleted before commiting and the `LOCAL` flag has to be set to `False`.

---
## How it works
1. Fetch CKM Change Requests: The script retrieves CKM Change Requests in “bite‑sized” chunks
2. From these lists it derives:
   - crids: IDs of all CKM CRs (CR-xxx)
   - closed_crids: IDs of closed CKM CRs (CR-xxx)
3. Fetch Jira issues: All Jira issues in the CLINICAL project are retrieved.
   - Calls the Jira search API with:
     - jql: the JQL defined above
     - nextPageToken: for pagination (Jira Cloud UI‑style pagination)
     - maxResults: 100 
     - fields: a list of required Jira custom fields and status
   - Returns:
     - all_issues: raw Jira issues as returned by the API
     - issue_info: a list of tuples with the following structure:
```
     (
      id,               # Jira issue ID
      key,              # Jira issue key, e.g. CLINICAL-123
      issuetype,        # Issue type name
      archetype_id,     # customfield_11295
      change_request_id,# customfield_11264 (numeric CR id without "CR-")
      ckm_concept_id,   # customfield_11295 (duplicate as per current code)
      modified_datetime,# customfield_11394 (CKM CR modified datetime)
      CR_priority,      # customfield_11266 (value)
      parent_status,    # customfield_11362
      CR_status,        # customfield_11262 (value)
      issue_status      # Jira status name
    )
```

4. Ensure parent issues exist: For each CKM CR, it inspects its parent CKM resource.
   - If not found it builds a parent_data JSON payload including:
     - summary = CKM resource display name
     - customfield_11265 = CKM resource CID
     - customfield_11295 = CKM resource main ID
     - customfield_11204 = CKM direct link
   - Depending on parent_type, it selects one of:
     - CKM_CR_to_JIRA_01_Create_Archetype_URL/TOKEN
     - CKM_CR_to_JIRA_02_Create_Template_URL/TOKEN

5. Create or update CR issues: For each CKM CR:
   - It derives the numeric CR ID without the CR- prefix:
   - It checks if a Jira issue exists with that CR ID.
     - If issue exists, but CR has changes, it calls `CKM_CR_to_JIRA_04_Update_CR_URL?issue=<key>`.
     - If issue does not exist, it calls `CKM_CR_to_JIRA_03_Create_CR_URL?issue=<parent_key>`
6. Move CRs to “In Progress”: For each CKM CR where the state is in `in-process`.
   - if the corresponging Jira issue state is not `In Progress`, `CKM_CR_to_JIRA_05_Move_to_In_Progress_URL?issue=<key>` is called to move the issue to this state.
7. Handle closed or missing CKM CRs: After processing all CKM CRs, the script loops over all Jira issues to determine which issues of CR have been closed in the CKM and which have no CR counterpart in the CKM.
   - if the CKM CR is closed, but the issue is not, `CKM_CR_to_JIRA_06_Add_close_comment_URL?issue=<key>` is called to add a comment to the Jira issue.
   - if there is no CKM CR, corresponding to the Jira issue, `Calls CKM_CR_to_JIRA_07_Add_missing_comment_URL?issue=<key>` is called to add a comment.
8. Summary output: At the end, the script prints and logs a summary:
```
I looked at the CLINICAL board!
Created Archetypes: <n>
Created Templates: <n>
Created Change Requests: <n>
Updated Change Requests: <n>
Moved Change Requests to IN_PROCESS: <n>
Added comment about closed CKM CR: <n>
Added comment about missing CKM CR: <n>
The same data is written to the log as a SUMMARY section.
```
---
## Logging
Logging is configured via setup_logger():
- Logger name: ckm_to_jira
- Level: INFO
- Outputs:
  - Rotating log file: log/ckm-to-jira.log
  - maxBytes = 100_000
  - backupCount = 5
  - Console (stdout), for visibility in CI logs
- Format:
  - `YYYY-MM-DD HH:MM:SS LEVEL ckm_to_jira - message`

>Example structured log entry:
>
>2026-01-01 12:00:00 INFO ckm_to_jira - jira_issue=CLINICAL-123 ckm_cr=CR-456  action=CREATE_CR  comment=Created an issue for the CR.
---
## Running the script
Clone/add the script to your repository.

Install dependencies:
```
pip install requests pandas
```

Configure environment variables
Set at least:
- jira_account
- jira_token
- All jira_webhook_0x_url and jira_webhook_0x_token variables.

Adjust mode flags in the script:
```
LOCAL = False      # or True, depending on how you provide credentials
READWRITE = True  
```


Run:
```
python CKM_CR_to_JIRA_issue_public.py
```
Check console output and log/ckm-to-jira.log to verify that the intended actions look correct.


