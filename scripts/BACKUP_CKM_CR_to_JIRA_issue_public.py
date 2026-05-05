import requests
from requests.auth import HTTPBasicAuth
import json
import os
import time
from datetime import datetime, timezone
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

version = "0.3.0"
LOCAL = False
READWRITE = False

# Jira instance info
JIRA_URL = "https://openehr.atlassian.net"
API_ENDPOINT = f"{JIRA_URL}/rest/api/2/issue"
SEARCH_ENDPOINT = f"{JIRA_URL}/rest/api/3/search/jql"
JIRA_BOARD = "CLINICAL"
# JQL expression to get all issues in the board
JQL = f"project = {JIRA_BOARD} ORDER BY key"

if LOCAL:
	pass
else:

	# Jira credentials
	EMAIL = os.environ["jira_account"]
	API_TOKEN = os.environ["jira_token"]

	#JIRA Automation webhooks
	CKM_CR_to_JIRA_01_Create_Archetype_URL = os.environ["jira_webhook_01_url"]
	CKM_CR_to_JIRA_01_Create_Archetype_TOKEN = os.environ["jira_webhook_01_token"]

	CKM_CR_to_JIRA_02_Create_Template_URL = os.environ["jira_webhook_02_url"]
	CKM_CR_to_JIRA_02_Create_Template_TOKEN = os.environ["jira_webhook_02_token"]

	CKM_CR_to_JIRA_03_Create_CR_URL = os.environ["jira_webhook_03_url"]
	CKM_CR_to_JIRA_03_Create_CR_TOKEN = os.environ["jira_webhook_03_token"]

	CKM_CR_to_JIRA_04_Update_CR_URL = os.environ["jira_webhook_04_url"]
	CKM_CR_to_JIRA_04_Update_CR_TOKEN = os.environ["jira_webhook_04_token"]

	CKM_CR_to_JIRA_05_Move_to_In_Progress_URL = os.environ["jira_webhook_05_url"]
	CKM_CR_to_JIRA_05_Move_to_In_Progress_TOKEN = os.environ["jira_webhook_05_token"]

	CKM_CR_to_JIRA_06_Add_close_comment_URL = os.environ["jira_webhook_06_url"]
	CKM_CR_to_JIRA_06_Add_close_comment_TOKEN = os.environ["jira_webhook_06_token"]

	CKM_CR_to_JIRA_07_Add_missing_comment_URL = os.environ["jira_webhook_07_url"]
	CKM_CR_to_JIRA_07_Add_missing_comment_TOKEN = os.environ["jira_webhook_07_token"]

# get list of CKM Change requests (CR)
# works with CKM version >= 1.21.0 
baseurl = "https://ckm.openehr.org"
header = {"accept": "application/json"}

counter_create_archetype = 0
counter_create_template = 0
counter_create_CR = 0
counter_update_CR = 0
counter_move_CR_INPROCESS = 0
counter_move_CR_DONE = 0
counter_report_missing = 0


def setup_logger():
	# Ensure the folder exists
	log_dir = Path("log")
	log_dir.mkdir(parents=True, exist_ok=True)

	logger = logging.getLogger("ckm_to_jira")
	logger.setLevel(logging.INFO)

	# Avoid duplicate handlers if script is imported/re-run in same process
	if logger.handlers:
		return logger

	file_handler = RotatingFileHandler(
		filename=log_dir / "ckm-to-jira.log",
		maxBytes=100_000,      # small on purpose so rotation happens in CI
		backupCount=5,        # keep up to 5 rotated files
		encoding="utf-8",
	)

	formatter = logging.Formatter(
		fmt="%(asctime)s %(levelname)s %(name)s - %(message)s",
		datefmt="%Y-%m-%d %H:%M:%S%z",
	)
	file_handler.setFormatter(formatter)

	# Optional: also log to stdout so you can see it in Actions logs
	console_handler = logging.StreamHandler()
	console_handler.setFormatter(formatter)

	logger.addHandler(file_handler)
	logger.addHandler(console_handler)
	logger.propagate = False

	return logger

def stop_script(message):
	logger.info(message)
	exit()

def get_JSON_from_CKM_size(url, header, size, max_chunks, parameter):
	print('Downloading JSON bite-sized')
	json_list = []
	offset = 0
	for _ in range(max_chunks):
		url_sized = f"{url}?size={size}&offset={offset}{parameter}"
		response = requests.get(url_sized, headers=header)
		if response.status_code != 200:
			print(f"Error: Received status code {response.status_code}")
			stop_script('Error: Could not connect to CKM to get CR.')
			break
		chunk = response.json()
		if not chunk:  # empty list
			break
		json_list.extend(chunk)
		offset += size
	return json_list

def get_all_issues(jql: str = JQL, batch_size: int = 100):

	all_issues = []
	issue_info = [] #we need a list of issues with
	nextPage = ''

	while True:
		query = {
			  'jql': jql,
			  'nextPageToken': nextPage,
			  'maxResults': 100,
			  'fields': ['customfield_11295',
						 'customfield_11264',
						 'customfield_11295',
						 "customfield_11394",
						 "customfield_11266",
						 "customfield_11362",
						 "customfield_11262",
						 "issuetype",
						 "status"],
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
			stop_script('Error: Could not connect to JIRA to get issues.')
			break

		data = response.json()
		issues = data.get("issues", [])

		for issue in issues:
			id = issue['id']
			key = issue['key']
			issuetype = issue['fields']['issuetype']['name']
			archetype_id = issue['fields']['customfield_11295']
			change_request_id = issue['fields']['customfield_11264']
			ckm_concept_id = issue['fields']['customfield_11295']
			issue_status = issue['fields']['status']['name']

			modified_datetime = issue['fields']["customfield_11394"]
			if issue['fields']["customfield_11266"]:
				CR_priority = issue['fields']["customfield_11266"]['value']
			else:
				CR_priority = "None"

			parent_status = issue['fields']["customfield_11362"]

			if issue['fields']["customfield_11262"]:
				CR_status = issue['fields']["customfield_11262"]['value']
			else:
				CR_status = "None"

			if not archetype_id:
				archetype_id = "None"
			if not change_request_id:
				change_request_id = "None"
			if not ckm_concept_id:
				ckm_concept_id = "None"
			if not CR_priority:
				CR_priority = "None"
			if not CR_status:
				CR_status = "None"

			#		0	1		2			3				4					5				6				7				8			 9			10
			info = (id, key, issuetype, archetype_id, change_request_id, ckm_concept_id, modified_datetime, CR_priority , parent_status, CR_status,  issue_status)
			issue_info.append(info)

		all_issues.extend(issues)

		print(f"Fetched {len(issues)} issues (total so far: {len(all_issues)})")

		if "nextPageToken" not in data.keys():
			break
		else:
			nextPage = data["nextPageToken"]

	return all_issues, issue_info


#start logging
logger = setup_logger()
logger.info(f"Script version {version}")
logger.info("Starting CKM CR → Jira issues.")

#get the information in JSON format

print('Getting Change Requests from', baseurl + '/ckm/rest/v1/change-requests')
changeRequest = get_JSON_from_CKM_size(baseurl + '/ckm/rest/v1/change-requests', header, 100, 100, "")
crids = [d["crId"] for d in changeRequest if "crId" in d]
print('Found ' + str(len(crids)) + ' Change Requests in the CKM')

print('Getting CLOSED Change Requests from', baseurl + '/ckm/rest/v1/change-requests?status=CLOSED')
closed_changeRequest = get_JSON_from_CKM_size(baseurl + '/ckm/rest/v1/change-requests', header, 100, 100, "&status=CLOSED")
closed_crids = [d["crId"] for d in closed_changeRequest if "crId" in d]
print('Found ' + str(len(closed_crids)) + ' closed Change Requests in the CKM')



print('Download issue from Jira...')
issues, issue_info = get_all_issues()
print('Number of issues', len(issue_info))

print('Checking for all CKM CRs...')
# for every CKM Chang Request...
#for CR in changeRequest:
for i in range(len(changeRequest)):
#for i in range(500):   #MAKE IT SO WE CAN ONLY SEND ONE CR TO JIRA
	CR = changeRequest[i]
	print('Looking at CR', CR['crId'])


	# does the "parent" of this change request exist?
	parent_type = CR['ckmResource']['resourceType']
	parent_id = CR['ckmResource']['resourceMainId']
	parent_cid = CR['ckmResource']['cid']
	parent_link = ""
	if parent_type == 'ARCHETYPE':
		parent_link = baseurl+'/ckm/archetypes/'+parent_cid
	elif parent_type == 'TEMPLATE':
		parent_link = baseurl+'/ckm/templates/'+parent_cid

	#parent_status = CR['ckmResource']['status']
	foundParent = next((t for t in issue_info if t[3] == parent_id), None)
	if foundParent:
		parent_key = foundParent[1]
		parent_status = foundParent[10]
		print('I found the parent:', parent_key)
	else:
		#create a new parent
		print('Did not find parent', parent_id)
		parent_data =  {
			  "data": {
				"summary": CR['ckmResource']['resourceMainDisplayName'],
				"customfield_11265": parent_cid,
				"customfield_11295": parent_id,
				"customfield_11204": parent_link
			  }
			}
		# Create the issue parent
		# counter_create_archetype += 1
		print(parent_type)
		if READWRITE:
		#if parent_type == 'TEMPLATE':
			issues, issue_info = get_all_issues()

			if parent_type == 'ARCHETYPE':
				URL = CKM_CR_to_JIRA_01_Create_Archetype_URL
				secret = CKM_CR_to_JIRA_01_Create_Archetype_TOKEN
				counter_create_archetype += 1
			elif parent_type == 'TEMPLATE':
				URL = CKM_CR_to_JIRA_02_Create_Template_URL
				secret = CKM_CR_to_JIRA_02_Create_Template_TOKEN
				counter_create_template += 1

			#CREATE THE ARCHETYPE OR TEMPLATE
			response = requests.post(
				URL,
				data=json.dumps(parent_data),
				headers={"Content-Type": "application/json", "Accept": "application/json", "X-Automation-Webhook-Token":secret}
			)
			print(response.status_code)
			if response.status_code != 200:
				stop_script('Error: Tried to execute Jira webhook to create a parent issue, but failed to connect.')

			#WAIT AND CONTROL IF THE THING WAS CREATED
			parent_key = ''
			time_waited = 0
			wait_time = 10
			max_time = 50

			while parent_key == '' and time_waited <max_time:
				#I have to wait for the item to be created - this is not the best way to do this, but we do not get info back from the webhook
				time.sleep(wait_time)
				time_waited += wait_time

				updated_issues, updated_issue_info = get_all_issues()
				added = list(set(updated_issue_info) - set(issue_info))

				foundCreatedParent = next((t for t in added if t[3] == parent_id), None)
				if foundCreatedParent:
					parent_key = foundCreatedParent[1]
					parent_status = foundCreatedParent[10]
					print('I created', parent_key, added)

				issue_info = updated_issue_info
			if parent_key == '':
				stop_script('Error: Tried to create a parent issue, but could not confirm the creation.')
		else:
			parent_key = 'DUMMYPARENTISSUE'
			print('ONLY READ MODE: I would have created a new parent here!')
			if parent_type == 'ARCHETYPE':
				counter_create_archetype += 1
			elif parent_type == 'TEMPLATE':
				counter_create_template += 1
		#logging change
		logger.info("jira_issue=%s	ckm_cr=%s	action=%s	comment=%s", parent_key, CR['crId'], 'CREATE_PARENT', 'Created a parent issue for this CR.')

	#check if the CR exists in the issues
	print('Looking for the CR in the issues...')
	CR_id_number = CR['crId'].replace('CR-','')
	foundIssue = next((t for t in issue_info if t[4] == CR_id_number), None)

	#pre-process the CR data
	label = CR['crId']
	resourceMainId = CR['ckmResource']['resourceMainId']
	#status = CR['ckmResource']['status']
	year = CR['modificationTime'][:4]
	summary = CR['title']
	issuetype = 'CKM change request'
	description =  CR['description']
	issue_data = {
			  "data": {
				"summary": summary,
				"description": description,
				"customfield_11394": CR['modificationTime'][:19] + '.000' + CR['modificationTime'][19:22] + '00' , 	#CKM CR modified datetime
				"customfield_11264": CR_id_number,				#CKM CR ID
				"customfield_11267": CR['creationTime'][:10], 		#CKM CR Created Date
				"customfield_11265": CR['ckmResource']['cid'],	#CKM Resource ID
				"customfield_11266_value": CR['priority'].lower(),	#CKM CR priority
				"customfield_11362": parent_status,					#parent status
				"customfield_11262_value": CR['status'].lower().replace('_','-'),		#CKM CR status
				"customfield_11204": CR['directLink']					#CKM link
			  }
			}
	issue_updatedata = {
			  "data": {
				"summary": summary,
				"description": description,
				"customfield_11394": CR['modificationTime'][:19] + '.000' + CR['modificationTime'][19:22] + '00' , 	#CKM CR modified datetime
				"customfield_11264": CR_id_number,				#CKM CR ID
				"customfield_11267": CR['creationTime'][:10], 		#CKM CR Created Date
				"customfield_11265": CR['ckmResource']['cid'],	#CKM Resource ID
				"customfield_11266_value": CR['priority'].lower(),	#CKM CR priority
				"customfield_11362": parent_status,					#parent status
				"customfield_11262_value": CR['status'].lower().replace('_','-'),		#CKM CR status
				"customfield_11204": CR['directLink']					#CKM link
			  }
			}

	issuekey = ''

	if foundIssue:
		#update the issue
		issuekey = foundIssue[1]
		print('I found the CR as issue', issuekey, label)

		#check if there are changes to update
		fmt = "%Y-%m-%dT%H:%M:%S.%f%z"

		def same_to_minute(a: str, b: str) -> bool:
			print(f'Comparing {a} vs {b}')

			if not a:
				a = '1707-05-01T00:00:00.000+0100'
			if not b:
				b = '1789-07-14T00:00:00.000+0100'

			dt_a = datetime.strptime(a, fmt).astimezone(timezone.utc)
			dt_b = datetime.strptime(b, fmt).astimezone(timezone.utc)
			return dt_a.replace(second=0, microsecond=0) == dt_b.replace(second=0, microsecond=0)

		has_changed = not (
		same_to_minute(foundIssue[6], CR['modificationTime'][:19] + '.000' + CR['modificationTime'][19:22] + '00') and 	#CKM CR modified datetime
		foundIssue[7] == CR['priority'].lower() and	#CKM CR priority
		foundIssue[8] == parent_status and					#parent status
		foundIssue[9] == CR['status'].lower().replace('_','-')		#CKM CR status
		)
		if has_changed:
			print('I found a change in this issue')
			print(foundIssue[6],'->' ,CR['modificationTime'][:19] + '.000' + CR['modificationTime'][19:22] + '00', same_to_minute(foundIssue[6], CR['modificationTime'][:19] + '.000' + CR['modificationTime'][19:22] + '00'))
			print(foundIssue[7],'->' ,CR['priority'].lower(), foundIssue[7] == CR['priority'].lower())
			print(foundIssue[8],'->' ,parent_status, foundIssue[8] == parent_status)
			print(foundIssue[9],'->' ,CR['status'].lower().replace('_','-'), foundIssue[9] == CR['status'].lower().replace('_','-'))


			print('I will update the issue!')
			counter_update_CR += 1
			#update
			if READWRITE:
				#update the information in JIRA
				URL = CKM_CR_to_JIRA_04_Update_CR_URL+'?issue='+issuekey
				secret = CKM_CR_to_JIRA_04_Update_CR_TOKEN
				print('Sending CR issue update to ' + URL)
				response = requests.post(
					URL,
					data=json.dumps(issue_updatedata),
					headers={"Content-Type": "application/json", "Accept": "application/json", "X-Automation-Webhook-Token":secret}
				)
				print(response)
				if response.status_code != 200:
					stop_script('Error: Tried to execute Jira webhook to update issue content, but failed to connect.')

			else:
				print('ONLY READ MODE: I would have update the CR here', issuekey, label)

			logger.info("jira_issue=%s	ckm_cr=%s	action=%s	comment=%s", issuekey, CR['crId'], 'UPDATE_CR', 'Updated the CR data in issue.')
	else:
		print('I have NOT found the issue for', label)
		#create the issue
		counter_create_CR += 1
		if READWRITE:
			URL = CKM_CR_to_JIRA_03_Create_CR_URL+'?issue='+parent_key
			secret = CKM_CR_to_JIRA_03_Create_CR_TOKEN
			response = requests.post(
				URL,
				data=json.dumps(issue_data),
				headers={"Content-Type": "application/json", "Accept": "application/json", "X-Automation-Webhook-Token":secret}
			)
			print(response.status_code)
			if response.status_code != 200:
				stop_script('Error: Tried to execute Jira webhook to create an issue, but failed to connect.')

			#WAIT AND CONTROL IF THE THING WAS CREATED
			issuekey = ''
			time_waited = 0
			wait_time = 10
			max_time = 50

			while issuekey == '' and time_waited <max_time:
				#I have to wait for the item to be created - this is not the best way to do this, but we do not get info back from the webhook
				time.sleep(wait_time)
				time_waited += wait_time

				updated_issues, updated_issue_info = get_all_issues()
				added = list(set(updated_issue_info) - set(issue_info))

				foundCreatedIssue = next((t for t in added if t[4] == CR_id_number), None)
				if foundCreatedIssue:
					issuekey = foundCreatedIssue[1]
					print('I created', issuekey, added)

				issue_info = updated_issue_info
				foundIssue = next((t for t in issue_info if t[4] == CR_id_number), None)
			if issuekey == '':
				stop_script('Error: Tried to execute Jira webhook to create an issue, but failed to connect.')

			print('I created issue', issuekey)

		else:
			issuekey = 'DUMMYISSUE'
			print('READ ONLY MODE: I would have created a new issue for this CR')

		logger.info("jira_issue=%s	ckm_cr=%s	action=%s	comment=%s", issuekey, CR['crId'], 'CREATE_CR', 'Created an issue for the CR.')


	if foundIssue and CR['status'] == 'IN_PROCESS':
		print('This CR is IN_PROCESS. I want to move it to "IN PROGRESS" in JIRA.')

		if foundIssue[10]!='In Progress':
			counter_move_CR_INPROCESS += 1
			if READWRITE:

				# CREATE WEBHOOK FOR THIS
				print('I am moving this to "in progress"!', label, issuekey)

				URL = CKM_CR_to_JIRA_05_Move_to_In_Progress_URL+'?issue='+issuekey
				secret = CKM_CR_to_JIRA_05_Move_to_In_Progress_TOKEN
				response = requests.post(
					URL,
					headers={"Content-Type": "application/json", "Accept": "application/json", "X-Automation-Webhook-Token":secret}
				)
				print(response.status_code)
				if response.status_code != 200:
					stop_script('Error: Tried to execute Jira webhook to move issue to IN PROGRESS, but failed to connect.')

			else:
				print('READ ONLY MODE: I would have shifted the CR to "start work', CR['crId'])

			logger.info("jira_issue=%s	ckm_cr=%s	action=%s	comment=%s", issuekey, CR['crId'], 'UPDATE_IN_PROGRESS', 'Updated issue state to "In Progress".')
		else:
			print('This was allready "In Progress". Nothing to do here.')



print('Now we check if there are JIRA issues that are not in the CKM CR list (a CR that has been closed.)...')
# for every CR labels in JIRA (not including new ones)
for info in issue_info:
	if info[4] != "None":
		#this is a Change request. Does it exist in the list of change requests
		if 'CR-'+info[4] in crids:
			print('This CR exists in the issues. Nothing to do here!')
			pass
		elif 'CR-'+info[4] in closed_crids:
			print('This CR was closed! We are going to add a comment!')

			#as this CR was closed in the CKM, propose to move it to "Done" in JIRA
			#but only if issue is not in "Rejected" or "Done"
			if info[10] != 'Rejected' and info[10] != 'Done':
				counter_move_CR_DONE += 1
				if READWRITE:
					issuekey = info[1]
					print('I found issue ' + issuekey + ' that has a CR-.. label, but is not an open CKM CR. I add a comment to JIRA.')

					URL = CKM_CR_to_JIRA_06_Add_close_comment_URL+'?issue='+issuekey
					secret = CKM_CR_to_JIRA_06_Add_close_comment_TOKEN
					response = requests.post(
						URL,
						headers={"Content-Type": "application/json", "Accept": "application/json", "X-Automation-Webhook-Token":secret}
					)
					print(response.status_code)
					if response.status_code != 200:
						stop_script('Error: Tried to execute Jira webhook to inform about a closed CR, but failed to connect.')
				else:
					issuekey = info[1]
					print('ONLY READ MODE: I found issue ' + issuekey + ' that has a CR-.. label, but is not an open CKM CR. I would transition this to "Done" in JIRA.')

				logger.info("jira_issue=%s	ckm_cr=%s	action=%s	comment=%s", issuekey, 'CR-'+info[4] , 'COMMENT_CLOSED', 'CR has been closed. Added comment to move issue to "Done" or "Rejected".')
		else:
			print('This issue has a CR that does not exist in the CKM!!!')
			#as this CR does not exist in the CKM, propose to move it to "Done" in JIRA

			if info[10] != 'Rejected' and info[10] != 'Done':
				counter_report_missing += 1
				if READWRITE:
					issuekey = info[1]
					print('I found issue ' + issuekey + ' that has a CR-.. label, but is not in the CKM. I add a comment to JIRA.')
					URL = CKM_CR_to_JIRA_07_Add_missing_comment_URL+'?issue='+issuekey
					secret = CKM_CR_to_JIRA_07_Add_missing_comment_TOKEN
					response = requests.post(
						URL,
						headers={"Content-Type": "application/json", "Accept": "application/json", "X-Automation-Webhook-Token":secret}
					)
					print(response.status_code)
					if response.status_code != 200:
						stop_script('Error: Tried to execute Jira webhook to inform about a missing CR, but failed to connect.')

				else:
					issuekey = info[1]
					print('ONLY READ MODE: I found issue ' + issuekey + ' that has a CR-.. label, but is not an open or closed CKM CR. I would add a comment in JIRA.')

				logger.info("jira_issue=%s	ckm_cr=%s	action=%s	comment=%s", issuekey, 'CR-'+info[4] , 'COMMENT_MISSING', 'CR not found in CKM. Added comment to move issue to "Done" or "Rejected".')

#print a report on the number of changes done
print(f'I looked at the {JIRA_BOARD} board!')
print(f'Created Archetypes: {counter_create_archetype}\n'
	  f'Created Templates: {counter_create_template}\n'
	  f'Created Change Requests: {counter_create_CR}\n'
	  f'Updated Change Requests: {counter_update_CR}\n'
	  f'Moved Change Requests to IN_PROCESS: {counter_move_CR_INPROCESS}\n'
	  f'Added comment about closed CKM CR: {counter_move_CR_DONE}\n'
	  f'Added comment about missing CKM CR: {counter_report_missing}'
	  )

logger.info('SUMMARY')
logger.info(f'Created Archetypes: {counter_create_archetype}')
logger.info(f'Created Templates: {counter_create_template}')
logger.info(f'Created Change Requests: {counter_create_CR}')
logger.info(f'Updated Change Requests: {counter_update_CR}')
logger.info(f'Moved Change Requests to IN_PROCESS: {counter_move_CR_INPROCESS}')
logger.info(f'Added comment about closed CKM CR: {counter_move_CR_DONE}')
logger.info(f'Added comment about missing CKM CR: {counter_report_missing}')

#end log
logger.info("Finished.")
