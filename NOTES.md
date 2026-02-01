# Notes

## 31/01/2026
### Phase 1
Phase 1 is just around setting up a service that will poll it's own email inbox looking for emails, and send and automated reply when it receives one.

First I set up the gmail and google cloud accounts for the Agent
Saved credentials in the project.
Wrote a gitignore so that I can make my repo without exposing creds.
Added my module requirements for using google apis
Created a venv to keep things clean

Wrote agent.py file to authenticate w/ Gmail API
Agent polls the email inbox for up to 10 emails
Agent extracts email details (sender body etc.)
Agent replies in the same thread
Agent only processes emails from whitelisted senders

GOOGLE SHUT DOWN MY ACCOUNT
I needed to create a new user under my google workspace instead.
Have now set it up under poolbeg solutions account and downloaded new creds
This time we made our client only accessible by "Internal" i.e. accounts within our workspace
We ran authentication to get our token.json file.... SUCCESS

Next I'm going to deploy to Render. I'll make sure the deployment process is working smoothly and test email receival and sending after deployment again. Then I'll add some real "agent" functionality

Our client will need to get the Gmail API token from env vars in Render now.
We've successfully deployed on Render. I tested that it's working.
Strangely there were no logs. Found out I need and the -u flag to the run command so that the output is unbuffered.

### Phase 2
Ok, now time to actually add an AI agent. I've created a new anthropic API key.
I've added anthropic to my reqs, not to update the agent.py file
I'm starting with my system prompt and I'm trying to give it a bit of personality. 
I've based it on Mr. Stevens, the butler from Remains of the Day. I'm thinking I'm going to use this as a writing agent, but I'm not really thinking about that too much yet.. just want a bit of personlity for the initial phase.

Added init_claude function. 
Looks for API key. Throws error if not found.

Updated process_email function
Instead of just creating a reply, it now creates a prompt based on the email received, and makes an api call to claude with the system prompt and this new user prompt.

Also made sure init_claude is called in run_agent after authenticating the gmail api.

Next I want to give the agent access to it's own github repo.
I want it to be able to create and edit txt and markdown files.
I've created a github account for James (Mr. Stevens) and a "workspace" repo
I;ve created a general access token for the account.
I also installed libraries for accessing github.
I updated system prompt to provide info about document creation
I also created a string containing the tools definitions, with info about the tools available to the model. In this case, just saving documents.
I realised I don't want to just create docs directly in the repo. I want to create files locally in a workspace folder, and commit and push them to the repo.
Same goes for editing. It should edit locally then commit changes and push to the repo.
I've updated the system prompt and tools list.
I've added a workspace class that will open a subprocess to manage the local workspace and commit to repo
I tried creating some files w/ commands sent by email

## 01/02/2026
Made good progress yesteday. Agent can scan email inbox, and process simple requests to make files and put them on github.
First port of call today is tidying up yesterday's work.
Once that's done I have some things I want to do.
I want to initialise the agent's personality on first deploy, and I want the agent to be able to self-modify its own personality.
I'm taking inspiration from OpenClaw for this, but will keep things a bit more conservative than they have.
Things I'm noting I want to fix during code review:
- Way too much config in this file
- I don't like the system prompt.. too gimmicky
- Can list document but not read them.
- Replies don't actually stay in the same thread
- No observability
- agent has no memory, so I can't instruct it to change its behaviour

I've moved out config
I've put the whitelisted users in an env var so I can use personal email address and not expose it in my repo
I've put prompts in their own folder.
I'm putting tools in their own folder. This involed building a tool handler. The tool handler has a handle_tool_call function which allows us to pass a tool name, it's input, along with the service object that carry out the execution or use of the tool. Initial example of this is our Workspace class. Objects instantiated from this class can be used to manage our git workspace.

Made a silly mistake where I forgot that env vars will just be loaded as a string. So when loading authorised senders I was actually loading "["example@gmail.com", "example2@gmail.com"]" and then of course it wasn't correclty checking the sender against the list. Needed to parse this as json when importing from env vars.

I've done some testing, and everything is working nicely again.

The agent's personality has been annoying me. I want it to be more subtle. I've reworded the prompt.
I've moved the email processing prompt out in to the prompts folder.

I've also moved the workspace class into it's own place in the services folder.
I created a new Email Service class in the services folder that handles everything relation to polling inbox, extracting details from emails, sending replies etc

I've noticed that agent replies are sent as new email threads, not replies to the original thread. I'm going to 
It looks like the id being used was the gmail internal ID, as opposed to the correct message ID header.

Now noticed that when I request it to update files, it does it just fine locally, but the changes aren't pushed to the repo.
Found the issue. It was silently failing. when the workspace already existed, the remote URL wasn't being updated with the authenticated token.




