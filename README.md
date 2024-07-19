# Teams Puppet
Manages microsoft accounts to retrieve teams JSON web tokens for automating tasks that are not supported by the graph API.

```python
import teams_puppet
import requests

puppet = teams_puppet.Puppet("email", "password")

headers = {
    "accept": "application/json",
    "Content-Type": "application/json",
    "authorization": "Bearer " + puppet.get_token(),
    "X-ClientType": "MicrosoftTeamsAngular",
    "X-HostAppRing": "general"
}

response = requests.get("https://teams.microsoft.com/api/example", headers=headers)
```

The token is fetched on puppet initialization. If the token expires, a new one will be fetched automatically.