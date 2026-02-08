import requests

class DiscordAuthHandler:
    def __init__(self, client_id, client_secret, redirect_uri, bot_token):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.bot_token = bot_token
        self.api_base = "https://discord.com/api/v10"

    def exchange_code(self, code):
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self.redirect_uri
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        response = requests.post(f"{self.api_base}/oauth2/token", data=data, headers=headers)
        return response.json()

    def add_member_to_guild(self, user_id, access_token, guild_id, role_id):
        url = f"{self.api_base}/guilds/{guild_id}/members/{user_id}"
        headers = {"Authorization": f"Bot {self.bot_token}"}
        # Adiciona o usuário ao servidor com o cargo específico
        payload = {
            "access_token": access_token,
            "roles": [str(role_id)]
        }
        return requests.put(url, headers=headers, json=payload)