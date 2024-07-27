# Teams Puppet
Manages microsoft accounts to retrieve teams JSON web tokens for automating tasks that are not supported by the graph API.

```python
import teams_puppet
import requests

puppet = teams_puppet.Puppet("email", "password")

headers = {
    "accept": "application/json",
    "Content-Type": "application/json",
    "authorization": "Bearer " + puppet.get_token("teams"),
    "X-ClientType": "MicrosoftTeamsAngular",
    "X-HostAppRing": "general"
}

response = requests.get("https://teams.microsoft.com/api/example", headers=headers)
```

The token is fetched on puppet initialization. If the token expires, a new one will be fetched automatically.

The puppet can either fetch the teams token that uses the Outlook backend scope or the token used to access loki.delve.office.com.

```python
puppet = teams_puppet.Puppet("email", "password")
teams_token = puppet.get_token("teams")
loki_token = puppet.get_token("loki")
```

## Installation
Available on PyPi
[pypi.org/project/teams-puppet/](https://pypi.org/project/teams-puppet/)
```bash
pip install teams-puppet
```
