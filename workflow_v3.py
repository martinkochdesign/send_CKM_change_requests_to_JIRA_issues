import requests
from requests.auth import HTTPBasicAuth
import json

# Jira credentials and instance info
JIRA_URL = "https://openehr.atlassian.net"
API_ENDPOINT = f"{JIRA_URL}/rest/api/2/issue"
SEARCH_ENDPOINT = f"{JIRA_URL}/rest/api/3/search/jql"
EMAIL = "martinandreaskoch@catsalut.cat"
API_TOKEN = "ATATT3xFfGF0lqfHihOICVZbhMunT3-fdiwQn6gjF8fCOFGmQft2wC3TNai3RWq_g5fYeOgiwiefg0vek62M_QMZp0rtehbvWH0cTR4fCdLjkRjhA-jdwuZpO5TaZbgklUXG1HNZcdY-r1l8URhHclRH5rn2n2WR2xIEWTZBNUE1WtZH24D2pCo=A491F9FE"
JIRA_BOARD = "TEST"

# get list of CKM Change requests (CR)
# works with CKM version >= 1.21.0 (CKM international is not updated)
URLS = [
    'https://ckm-test.oceaninformatics.com',    #0
    'https://arketyper.no',                     #1
    'https://ckm.salut.gencat.cat/',            #2
    'https://ckm.openehr.org'                   #3
]


baseurl = URLS[3] #select the url you want to query
header = {"accept": "application/json"}

def get_JSON_from_CKM_size(url, header, size, max_chunks=100):
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

#get the information in JSON format
print('Getting Change Requests from', baseurl + '/ckm/rest/v1/change-requests')
changeRequest = get_JSON_from_CKM_size(baseurl + '/ckm/rest/v1/change-requests',header,100)

crids = [d["crId"] for d in changeRequest if "crId" in d]
print('Found ' + str(len(crids)) + ' Change Requests in the CKM')

# get list of Jira issue
JQL = f"project = {JIRA_BOARD} ORDER BY key"


def get_all_issues(jql: str = JQL, batch_size: int = 100):

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


print('Download issue from Jira...')
issues = get_all_issues()
print('Number of issues', len(issues))


issuelabels =  [item for obj in issues for item in obj['fields'].get("labels", [])]

print('Checking for all CKM CRs...')
# for every CKM CR...
for CR in changeRequest:
	# CR exists in JIRA as label?
	#first generate the things we need
	label = CR['crId']
	summary = CR['crId'] + ' - ' + CR['title']
	issuetype = CR['ckmResource']['resourceType'].title()
	description = \
		CR['ckmResource']['resourceType'] + ': ' + CR['ckmResource']['resourceMainDisplayName'] + ' (' + CR['ckmResource']['status'] + ')\n\n' +\
		'Description: ' + CR['description'] + '\n\n' +\
		'Status: ' + CR['status'] + '\n\n' +\
		'Last updated: ' + CR['modificationTime'] + '\n\n' +\
		'Link: ' + CR['directLink'] + '\n\n' +\
		''
	issue_data = {
			  "fields": {
				"project": {
				  "key": JIRA_BOARD               # <-- your Jira project key
				},
				"summary": summary,
				"description": description,
				"issuetype": {
				  "name": issuetype              # or "Story", "Change Request", etc.
				},
				"priority": {
				  "name": "Medium"            # map from your PRIORITY value
				},
				"labels": [
				  label
				],
			  }
			}
	issue_updatedata = {
			  "fields": {
				"project": {
				  "key": JIRA_BOARD               # <-- your Jira project key
				},
				"summary": summary,
				"description": description,
				"issuetype": {
				  "name": issuetype              # or "Story", "Change Request", etc.
				}
			  }
			}

	issuekey = ''
	if CR['crId'] in issuelabels:
		#yes -> update the CR information
		#first find the issue key
		for issue in issues:
			if CR['crId'] in issue['fields']['labels']:
				print(CR['crId'] + ' already exists in the JIRA issues.')
				issuekey = issue['key']
				print('Issue Key:',issuekey)
				#update
				update_endpoint = f"{JIRA_URL}/rest/api/2/issue/{issuekey}"
				print('Sending CR description and summary update to ' + update_endpoint)
				response = requests.put(
					update_endpoint,
					data=json.dumps(issue_updatedata),
					headers={"Content-Type": "application/json", "Accept": "application/json"},
					auth=HTTPBasicAuth(EMAIL, API_TOKEN)
				)

				break

	else:
		#no -> create a new issue
		print(CR['crId'] + ' does NOT exist in the JIRA issues. I create it!')
		# Create the issue
		response = requests.post(
			API_ENDPOINT,
			data=json.dumps(issue_data),
			headers={"Content-Type": "application/json", "Accept": "application/json"},
			auth=HTTPBasicAuth(EMAIL, API_TOKEN)
		)
		issuekey = response.json()["key"]

	if CR['status'] == 'IN_PROCESS':
		print('This CR is IN_PROCESS. I move it to "IN PROGRESS" in JIRA.')
		transition_id = "2"  # The ID you found for the "Start work" transition
		url = f"{JIRA_URL}/rest/api/3/issue/{issuekey}/transitions"
		payload = {
						"transition": {
							"id": transition_id
						}
					}
		response = requests.post(url, headers=header, auth=HTTPBasicAuth(EMAIL, API_TOKEN), json=payload)

print('Now we check if there are JIRA issues that are not in the CKM CR list (a CR that has been closed.)...')
# for every CR labels in JIRA (not including new ones)
for issue in issues:
	labels = issue['fields'].get('labels') or []  # safely handle None / missing / empty
	# CR exists in CKM?
	if any(label in crids for label in labels):
		#yes -> pass
		pass
	else:
		#no -> move JIRA issue to "Done"
		issue_key = issue['key']
		#does this issue have a CR-NN label?
		if any(label.startswith("CR-") for label in labels):
			print('I found issue ' + issue_key + ' that has a CR-.. label, but is not an open CKM CR. I transition this to "Deprecated" in JIRA.')
			transition_id = "9"  # The ID you found for the "Done" transition
			url = f"{JIRA_URL}/rest/api/3/issue/{issue_key}/transitions"
			payload = {
							"transition": {
								"id": transition_id
							}
						}
			response = requests.post(url, headers=header, auth=HTTPBasicAuth(EMAIL, API_TOKEN), json=payload)
