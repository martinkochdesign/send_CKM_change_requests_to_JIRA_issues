<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>CKM Change Requests ↔ Jira Sync Script – README</title>
</head>
<body>

  <h1>CKM Change Requests ↔ Jira Sync Script</h1>

  <p>
    This script synchronizes openEHR CKM Change Requests (CRs) with Jira issues in a given Jira project/board.
    It can:
  </p>

  <ol>
    <li>Download all CKM Change Requests from a CKM instance.</li>
    <li>Download all Jira issues in a specific Jira project.</li>
    <li>
      For each CKM CR:
      <ul>
        <li>If a Jira issue with a matching label (<code>CR-...</code>) already exists, update its summary and description.</li>
        <li>If it does not exist, create a new Jira issue.</li>
        <li>If the CKM CR is <code>IN_PROCESS</code>, transition the Jira issue to “In Progress”.</li>
      </ul>
    </li>
    <li>
      For each Jira issue with a <code>CR-...</code> label that is no longer present in CKM (closed/removed CR),
      transition the issue to “Deprecated”.
    </li>
  </ol>

  <hr />

  <h2>Prerequisites</h2>

  <ul>
    <li>Python 3.x</li>
    <li>
      A Jira Cloud instance with:
      <ul>
        <li>API access enabled</li>
        <li>A Jira project key (e.g. <code>TEST</code>)</li>
        <li>
          A user with permissions to:
          <ul>
            <li>Browse issues</li>
            <li>Create issues</li>
            <li>Edit issues</li>
            <li>Transition issues</li>
          </ul>
        </li>
      </ul>
    </li>
    <li>
      A CKM instance (version ≥ 1.21.0) with the
      <code>/ckm/rest/v1/change-requests</code> endpoint enabled.
    </li>
  </ul>

  <hr />

  <h2>Installation</h2>

  <ol>
    <li>
      <p><strong>Clone or copy the script</strong> into a directory, e.g.:</p>
      <pre><code>mkdir ckm-jira-sync
cd ckm-jira-sync
# save the script as ckm_jira_sync.py
</code></pre>
    </li>
    <li>
      <p><strong>Create a virtual environment</strong> (optional but recommended):</p>
      <pre><code>python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows
</code></pre>
    </li>
    <li>
      <p><strong>Install dependencies:</strong></p>
      <pre><code>pip install requests
</code></pre>
    </li>
  </ol>

  <hr />

  <h2>Configuration</h2>

  <p>At the top of the script, configure:</p>

  <pre><code>JIRA_URL = "https://openehr.atlassian.net"        # Your Jira base URL
API_ENDPOINT = f"{JIRA_URL}/rest/api/2/issue"
SEARCH_ENDPOINT = f"{JIRA_URL}/rest/api/3/search/jql"

EMAIL = "your-email@example.com"
API_TOKEN = "your-jira-api-token"                 # NEVER commit real tokens to version control
JIRA_BOARD = "TEST"                               # Jira project key
</code></pre>

  <h3>Security note</h3>

  <ul>
    <li>
      The <code>API_TOKEN</code> is currently hard-coded in the example.
      <strong>This is not recommended</strong> for real use.
    </li>
    <li>
      Prefer one of these approaches:
      <ul>
        <li>
          <strong>Environment variables</strong>:
          <pre><code>import os
EMAIL = os.environ["JIRA_EMAIL"]
API_TOKEN = os.environ["JIRA_API_TOKEN"]
</code></pre>
          And set them in your shell:
          <pre><code>export JIRA_EMAIL="your-email@example.com"
export JIRA_API_TOKEN="your-token"
</code></pre>
        </li>
        <li>
          A local config file that is <strong>not</strong> checked into version control
          (e.g. <code>.env</code>, <code>config.json</code>).
        </li>
      </ul>
    </li>
  </ul>

  <h3>Selecting the CKM instance</h3>

  <p>The script provides a list of CKM base URLs:</p>

  <pre><code>URLS = [
    'https://ckm-test.oceaninformatics.com',    # 0
    'https://arketyper.no',                     # 1
    'https://ckm.salut.gencat.cat/',            # 2
    'https://ckm.openehr.org'                   # 3
]

baseurl = URLS[3]  # select the URL you want to query
</code></pre>

  <p>Change <code>baseurl</code> to point to the CKM instance you want to sync with, for example:</p>

  <pre><code>baseurl = URLS[0]  # use Ocean test CKM
</code></pre>

  <hr />

  <h2>How It Works</h2>

  <h3>1. Fetch CKM Change Requests</h3>

  <p>
    The function <code>get_JSON_from_CKM_size</code> retrieves CRs in paginated “bites”:
  </p>

  <pre><code>def get_JSON_from_CKM_size(url, header, size, max_chunks=100):
    print('Downloading JSON bite-sized')
    json_list = []
    offset = 0
    for _ in range(max_chunks):
        url_sized = f"{url}?size={size}&offset={offset}"
        response = requests.get(url_sized, headers=header)
        if response.status_code != 200:
            print(f"Error: Received status code {response.status_code}")
            break
        chunk = response.json()
        if not chunk:  # empty list
            break
        json_list.extend(chunk)
        offset += size
    return json_list
</code></pre>

  <p>It is then used as:</p>

  <pre><code>changeRequest = get_JSON_from_CKM_size(
    baseurl + '/ckm/rest/v1/change-requests',
    header,
    100
)
</code></pre>

  <ul>
    <li><code>changeRequest</code> becomes a list of CR objects from CKM.</li>
    <li>
      <code>crids</code> is a list of all <code>crId</code> values:
      <pre><code>crids = [d["crId"] for d in changeRequest if "crId" in d]
</code></pre>
    </li>
  </ul>

  <h3>2. Fetch Jira Issues for the Project</h3>

  <p>The script constructs a JQL to select all issues in the configured project:</p>

  <pre><code>JQL = f"project = {JIRA_BOARD} ORDER BY key"
</code></pre>

  <p>
    and uses <code>get_all_issues</code> to query Jira via the
    <code>/rest/api/3/search/jql</code> endpoint:
  </p>

  <pre><code>def get_all_issues(jql: str = JQL, batch_size: int = 100):
    all_issues = []
    nextPage = ''

    while True:
        query = {
            'jql': jql,
            'nextPageToken': nextPage,
            'maxResults': 100,
            'fields': ['labels'],
        }

        response = requests.request(
            "GET",
            SEARCH_ENDPOINT,
            headers=header,
            params=query,
            auth=HTTPBasicAuth(EMAIL, API_TOKEN)
        )

        if response.status_code != 200:
            print("Error:", response.status_code, response.text)
            break

        data = response.json()
        issues = data.get("issues", [])
        all_issues.extend(issues)

        print(f"Fetched {len(issues)} issues (total so far: {len(all_issues)})")

        if "nextPageToken" not in data.keys():
            break
        else:
            nextPage = data["nextPageToken"]

    return all_issues
</code></pre>

  <p>
    All issues are accumulated in <code>issues</code>, and all labels are flattened
    into <code>issuelabels</code>.
  </p>

  <h3>3. Sync Each CKM CR to Jira</h3>

  <p>For each CR in <code>changeRequest</code>:</p>

  <ul>
    <li>
      A Jira label, summary, issue type, and description are built:
      <pre><code>label = CR['crId']
summary = CR['crId'] + ' - ' + CR['title']
issuetype = CR['ckmResource']['resourceType'].title()
description = \
    CR['ckmResource']['resourceType'] + ': ' + CR['ckmResource']['resourceMainDisplayName'] + ' (' + CR['ckmResource']['status'] + ')\n\n' +\
    'Description: ' + CR['description'] + '\n\n' +\
    'Status: ' + CR['status'] + '\n\n' +\
    'Last updated: ' + CR['modificationTime'] + '\n\n' +\
    'Link: ' + CR['directLink'] + '\n\n'
</code></pre>
    </li>
    <li>
      Payloads for creating and updating issues are constructed, including:
      <ul>
        <li><code>project</code> key</li>
        <li><code>summary</code></li>
        <li><code>description</code></li>
        <li><code>issuetype</code> (e.g. <code>Archetype</code>, <code>Template</code>)</li>
        <li><code>priority</code> (hard-coded as <code>"Medium"</code> for new issues)</li>
        <li><code>labels</code> containing the CR id (<code>"CR-..."</code>)</li>
      </ul>
    </li>
    <li>
      If a Jira issue already exists with that label, the script:
      <ul>
        <li>Finds the issue (by scanning <code>issues</code>).</li>
        <li>Updates its <code>summary</code> and <code>description</code> via
          <code>PUT /rest/api/2/issue/{issueKey}</code>.
        </li>
      </ul>
    </li>
    <li>
      If no Jira issue exists with that label, the script:
      <ul>
        <li>Creates a new issue via <code>POST /rest/api/2/issue</code>.</li>
      </ul>
    </li>
  </ul>

  <h4>Handling <code>IN_PROCESS</code> CRs</h4>

  <p>
    If the CKM CR has <code>status == 'IN_PROCESS'</code>, the script transitions the
    corresponding Jira issue to “In Progress”:
  </p>

  <pre><code>if CR['status'] == 'IN_PROCESS':
    print('This CR is IN_PROCESS. I move it to "IN PROGRESS" in JIRA.')
    transition_id = "2"  # The ID you found for the "Start work" transition
    url = f"{JIRA_URL}/rest/api/3/issue/{issuekey}/transitions"
    payload = {
        "transition": {
            "id": transition_id
        }
    }
    response = requests.post(url, headers=header, auth=HTTPBasicAuth(EMAIL, API_TOKEN), json=payload)
</code></pre>

  <p>
    <strong>Note:</strong> The transition ID <code>"2"</code> must match the workflow of your Jira project.
    You may need to adjust it.
  </p>

  <h3>4. Deprecate Jira Issues with Closed/Removed CRs</h3>

  <p>After syncing all CRs:</p>

  <ul>
    <li>
      For each Jira issue originally fetched:
      <ul>
        <li>
          If it has any <code>CR-...</code> label that is <strong>not</strong> in the current CKM
          <code>crids</code>, the issue is treated as corresponding to a closed/removed CKM CR.
        </li>
        <li>
          Such an issue is transitioned to “Deprecated” using transition ID <code>"9"</code>:
          <pre><code>transition_id = "9"  # The ID you found for the "Done" transition
url = f"{JIRA_URL}/rest/api/3/issue/{issue_key}/transitions"
payload = {
    "transition": {
        "id": transition_id
    }
}
response = requests.post(url, headers=header, auth=HTTPBasicAuth(EMAIL, API_TOKEN), json=payload)
</code></pre>
        </li>
      </ul>
    </li>
  </ul>

  <p>
    Again, <code>"9"</code> must be a valid transition ID in your Jira workflow for moving an issue to a
    “Deprecated” (or equivalent) status.
  </p>

  <hr />

  <h2>Running the Script</h2>

  <p>From the directory containing the script:</p>

  <pre><code>python ckm_jira_sync.py
</code></pre>

  <p>The script will print progress information to the console, e.g.:</p>

  <ul>
    <li>“Getting Change Requests from …”</li>
    <li>“Found N Change Requests in the CKM”</li>
    <li>“Download issue from Jira…”</li>
    <li>
      For each CR:
      <ul>
        <li>Whether it already exists in Jira or is created</li>
        <li>Any transitions made</li>
      </ul>
    </li>
    <li>
      For each outdated Jira issue:
      <ul>
        <li>A message that it is being transitioned to “Deprecated”</li>
      </ul>
    </li>
  </ul>

  <hr />

  <h2>Customization</h2>

  <ul>
    <li>
      <strong>Project key / board</strong>: set <code>JIRA_BOARD</code> to your desired project key.
    </li>
    <li>
      <strong>CKM instance</strong>: change <code>baseurl</code> to one of the URLs in <code>URLS</code> or add your own.
    </li>
    <li>
      <strong>Issue type mapping</strong>: currently derived from
      <code>CR['ckmResource']['resourceType'].title()</code>.
      You may map CKM resource types to specific Jira issue types, for example:
      <pre><code>type_map = {
    "archetype": "Change Request",
    "template": "Story",
}
issuetype = type_map.get(CR['ckmResource']['resourceType'].lower(), "Task")
</code></pre>
    </li>
    <li>
      <strong>Priority mapping</strong>: currently hard-coded to <code>"Medium"</code>.
      You can map CKM fields to Jira priorities.
    </li>
    <li>
      <strong>Transitions</strong>: update <code>transition_id</code> values
      (<code>"2"</code>, <code>"9"</code>) to match your Jira workflow.
    </li>
  </ul>

  <hr />

  <h2>Caveats and Notes</h2>

  <ul>
    <li>
      This script assumes:
      <ul>
        <li>CKM CR IDs follow the <code>CR-...</code> pattern used as Jira labels.</li>
        <li>The Jira user (<code>EMAIL</code>/<code>API_TOKEN</code>) has appropriate permissions.</li>
      </ul>
    </li>
    <li>
      Error handling is minimal:
      <ul>
        <li>For non-200 responses, it prints the status code and response text.</li>
        <li>
          In production, you should add:
          <ul>
            <li>Retry logic for transient network errors.</li>
            <li>More robust logging.</li>
            <li>Handling of Jira API limits.</li>
          </ul>
        </li>
      </ul>
    </li>
    <li>Do not commit real API tokens to public repositories.</li>
  </ul>

  <hr />

  <h2>License</h2>

  <pre><code>MIT License

Copyright (c) ...

Permission is hereby granted, free of charge, to any person obtaining a copy
...
</code></pre>

</body>
</html>