# CKM Change Requests to Jira issue Updater
> Script version: `0.5.0`

Synchronizes Change Requests (CRs) from the [openEHR Clinical Knowledge Manager (CKM)](https://ckm.openehr.org/ "https://ckm.openehr.org") to the [openEHR Jira CLINICAL board](https://openehr.atlassian.net/ "https://openehr.atlassian.net"), keeping Jira issues in sync with the CKM as the source of truth.

## What it does

The script performs a one-way sync from CKM → Jira:

1. **Fetches all Change Requests** from the CKM REST API (open and closed).
2. **Fetches all issues** from the Jira `CLINICAL` board.
3. **For each CKM Change Request:**
    - Creates the parent Archetype or Template issue in Jira if it doesn't exist.
    - Creates a new Jira issue for the CR if one doesn't exist yet.
    - Updates the Jira issue if the CR data has changed (modification time, priority, status, or parent status).
    - Transitions the Jira issue to "In Progress" if the CR status is `IN_PROCESS`.
    
4. **Detects closed or missing CRs:**
    - If a Jira issue references a CR that is now **closed** in CKM, it adds a comment and a `ClosedCR` label.
    - If a Jira issue references a CR that **doesn't exist** in CKM at all, it adds a comment and a `MissingCR` label.
    
5. **Logs** all actions to a rotating log file and prints a summary report.
    

## Requirements

- Python 3.8+
- Dependencies:
    `requests`
- CKM instance running version **≥ 1.21.0**
    

## Environment Variables

|Variable|Description|
|---|---|
|`jira_account`|Jira account email for API authentication|
|`jira_token`|Jira API token|
|`jira_webhook_01_url`|Webhook URL — Create Archetype|
|`jira_webhook_01_token`|Webhook token — Create Archetype|
|`jira_webhook_02_url`|Webhook URL — Create Template|
|`jira_webhook_02_token`|Webhook token — Create Template|
|`jira_webhook_03_url`|Webhook URL — Create CR|
|`jira_webhook_03_token`|Webhook token — Create CR|
|`jira_webhook_04_url`|Webhook URL — Update CR|
|`jira_webhook_04_token`|Webhook token — Update CR|
|`jira_webhook_05_url`|Webhook URL — Move to In Progress|
|`jira_webhook_05_token`|Webhook token — Move to In Progress|
|`jira_webhook_06_url`|Webhook URL — Add close comment|
|`jira_webhook_06_token`|Webhook token — Add close comment|
|`jira_webhook_07_url`|Webhook URL — Add missing comment|
|`jira_webhook_07_token`|Webhook token — Add missing comment|
|`jira_webhook_08_url`|Webhook URL — Add label|
|`jira_webhook_08_token`|Webhook token — Add label|

## Configuration

Two flags at the top of the script control its behavior:

| Flag        | Default | Description                                                                                                                        |
| ----------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `LOCAL`     | `False` | When `True`, skips loading credentials from environment variables (for local testing).                                             |
| `READWRITE` | `True`  | When `True`, the script creates/updates Jira issues. When `False`, it runs in **read-only mode** and only logs what it _would_ do. |

## Usage

`# Set environment variables (or use your CI secrets) export jira_account="you@example.com" export jira_token="your-api-token" export jira_webhook_01_url="https://..." export jira_webhook_01_token="..." # ... set all webhook env vars ... # Run the sync python ckm_cr_to_jira.py`

### Dry run (read-only mode)

Set `READWRITE = False` in the script to preview all actions without making any changes in Jira.

## Logging

Logs are written to `log/ckm-to-jira.log` using a rotating file handler (100 KB max, 5 backups). Each log entry includes the Jira issue key, CKM CR ID, action taken, and a comment. Output is also mirrored to stdout.

### Log actions

|Action|Description|
|---|---|
|`CREATE_PARENT`|Created an Archetype or Template parent issue|
|`CREATE_CR`|Created a Jira issue for a Change Request|
|`UPDATE_CR`|Updated an existing Jira issue with new CR data|
|`UPDATE_IN_PROGRESS`|Transitioned a Jira issue to "In Progress"|
|`COMMENT_CLOSED`|Added a comment about a closed CR|
|`COMMENT_MISSING`|Added a comment about a CR not found in CKM|

## How it works

The script uses **Jira Automation webhooks** (not direct API writes) to create and update issues, then polls the Jira API to confirm each creation before proceeding.

## Custom Fields
Customfields addressed in the Jira Work items.

|Field ID|Purpose|
|---|---|
|`customfield_11264`|CKM Change Request ID|
|`customfield_11265`|CKM Resource CID|
|`customfield_11266`|CKM CR Priority|
|`customfield_11267`|CKM CR Created Date|
|`customfield_11295`|CKM Resource Main ID (Archetype/Template)|
|`customfield_11362`|Parent issue status|
|`customfield_11394`|CKM CR Modified Datetime|
|`customfield_11262`|CKM CR Status|
|`customfield_11204`|CKM direct link|



