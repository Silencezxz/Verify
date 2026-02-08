from flask import Flask, request, redirect, session, url_for, render_template_string
import requests
import os
from dotenv import load_dotenv
from auth_handler import DiscordAuthHandler

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your_secret_key_here')  # Use env var for security

# OAuth2 Config
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI', 'https://your-railway-app-url.up.railway.app/callback')  # Set this to your Railway URL
BOT_TOKEN = os.getenv('BOT_TOKEN')  # Your bot token

auth_handler = DiscordAuthHandler(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, BOT_TOKEN)

# Guilds and roles to add the user to after verification
GUILDS_TO_ADD = [
    {'guild_id': 1404912975181123584, 'role_id': 1404919760617214067},
    # Add more guilds here if needed, e.g., {'guild_id': another_guild_id, 'role_id': another_role_id}
]

# Simple user storage (in production, use a database)
users = {}

@app.route('/')
def home():
    user = session.get('user')
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Syntax's Back - Home</title>
        <style>
            body { font-family: Arial, sans-serif; background: linear-gradient(135deg, #9b59b6, #71368a); color: white; margin: 0; padding: 0; }
            header { display: flex; justify-content: space-between; align-items: center; padding: 20px; background: rgba(0,0,0,0.5); }
            .logo { font-size: 24px; font-weight: bold; }
            .nav { display: flex; gap: 20px; }
            .nav a { color: white; text-decoration: none; }
            .sign-in-btn { background: #e91e63; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }
            .hero { text-align: center; padding: 100px 20px; }
            .hero h1 { font-size: 48px; margin-bottom: 20px; }
            .hero p { font-size: 24px; margin-bottom: 40px; }
            .btn { background: #e91e63; color: white; padding: 15px 30px; border: none; border-radius: 5px; font-size: 18px; cursor: pointer; }
            .modal { display: none; position: fixed; z-index: 1; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.4); }
            .modal-content { background-color: #fefefe; margin: 15% auto; padding: 20px; border: 1px solid #888; width: 80%; max-width: 400px; border-radius: 10px; }
            .close { color: #aaa; float: right; font-size: 28px; font-weight: bold; cursor: pointer; }
            .close:hover { color: black; }
            form { display: flex; flex-direction: column; }
            input { margin-bottom: 10px; padding: 10px; border: 1px solid #ccc; border-radius: 5px; }
            button { background: #9b59b6; color: white; padding: 10px; border: none; border-radius: 5px; cursor: pointer; }
        </style>
    </head>
    <body>
        <header>
            <div class="logo">Syntax's Back</div>
            <nav class="nav">
                <a href="/">Home</a>
                <a href="/account">Account</a>
                {% if user %}
                    <a href="/logout">Logout</a>
                {% else %}
                    <button class="sign-in-btn" onclick="openModal()">Sign In</button>
                {% endif %}
            </nav>
        </header>
        <section class="hero">
            <h1>Welcome to Syntax's Back</h1>
            <p>Join our community and get verified instantly.</p>
            <button class="btn" onclick="openModal()">Get Started Free</button>
        </section>
        <div id="signInModal" class="modal">
            <div class="modal-content">
                <span class="close" onclick="closeModal()">&times;</span>
                <h2>Sign In / Register</h2>
                <div id="modalContent">
                    <p>Welcome to <strong>Syntax's Back</strong>! To ensure a safe and bot-free community, we use <strong>OAuth2 verification</strong>.</p>
                    <p>This process authorizes your Discord account securely and adds you to the server automatically.</p>
                    <p><strong>Verification Steps:</strong></p>
                    <ol>
                        <li>Read the detailed rules below.</li>
                        <li>Click 'Sign In with Discord'.</li>
                        <li>Authorize the app in the popup.</li>
                        <li>You will be added to the server and verified instantly.</li>
                    </ol>
                    <p><strong>Why verify?</strong></p>
                    <ul>
                        <li>Prevents bots and spam accounts.</li>
                        <li>Ensures only real users join.</li>
                        <li>Protects our community from raids and abuse.</li>
                        <li>Uses Discord's official OAuth2 for security.</li>
                    </ul>
                    <p><strong>Benefits after verification:</strong></p>
                    <ul>
                        <li>Full access to all channels.</li>
                        <li>Participate in chats, events, and giveaways.</li>
                        <li>Gain XP and level up by chatting.</li>
                        <li>Use slash commands like /suggestion and /level.</li>
                        <li>Enjoy our beautiful lilac/purple theme.</li>
                    </ul>
                    <p><strong>Detailed Rules Summary:</strong></p>
                    <p><strong>1. Respect & Behavior:</strong> No insults, harassment, hate speech, or discrimination. Keep discussions civil.</p>
                    <p><strong>2. Content Policy:</strong> NSFW, illegal, or disturbing content is forbidden. Avoid toxic language.</p>
                    <p><strong>3. Spam & Advertising:</strong> No spamming messages, reactions, or links. External ads require staff approval.</p>
                    <p><strong>4. Security & Privacy:</strong> Never share personal data. Scams, phishing, or malicious activity leads to bans.</p>
                    <p><strong>5. Staff Decisions:</strong> Respect staff and their decisions. Appeal punishments calmly.</p>
                    <p><strong>6. Channel Usage:</strong> Use channels for their intended purpose. Read pins and descriptions.</p>
                    <button onclick="translateModal()">🌐 Translate to Portuguese</button>
                    <form action="/login" method="get">
                        <button type="submit">Sign In with Discord</button>
                    </form>
                </div>
            </div>
        </div>
        <script>
            function openModal() {
                document.getElementById('signInModal').style.display = 'block';
            }
            function closeModal() {
                document.getElementById('signInModal').style.display = 'none';
            }
            function translateModal() {
                const modalContent = document.getElementById('modalContent');
                if (modalContent.innerHTML.includes('Welcome to <strong>Syntax\'s Back</strong>')) {
                    modalContent.innerHTML = `
                        <p>Bem-vindo ao <strong>Syntax's Back</strong>! Para garantir uma comunidade segura e livre de bots, usamos <strong>verificação OAuth2</strong>.</p>
                        <p>Este processo autoriza sua conta Discord de forma segura e adiciona você ao servidor automaticamente.</p>
                        <p><strong>Passos de Verificação:</strong></p>
                        <ol>
                            <li>Leia as regras detalhadas abaixo.</li>
                            <li>Clique em 'Entrar com Discord'.</li>
                            <li>Autorize o aplicativo no popup.</li>
                            <li>Você será verificado e adicionado ao servidor instantaneamente.</li>
                        </ol>
                        <p><strong>Por que verificar?</strong></p>
                        <ul>
                            <li>Previne contas de bots e spam.</li>
                            <li>Garante que apenas usuários reais entrem.</li>
                            <li>Protege nossa comunidade contra raids e abusos.</li>
                            <li>Usa OAuth2 oficial do Discord para segurança.</li>
                        </ul>
                        <p><strong>Benefícios após verificação:</strong></p>
                        <ul>
                            <li>Acesso total a todos os canais.</li>
                            <li>Participe de chats, eventos e sorteios.</li>
                            <li>Ganhe XP e suba de nível conversando.</li>
                            <li>Use comandos slash como /suggestion e /level.</li>
                            <li>Aproveite nosso belo tema lilás/roxo.</li>
                        </ul>
                        <p><strong>Resumo Detalhado das Regras:</strong></p>
                        <p><strong>1. Respeito & Comportamento:</strong> Sem insultos, assédio, discurso de ódio ou discriminação. Mantenha discussões civis.</p>
                        <p><strong>2. Política de Conteúdo:</strong> Conteúdo NSFW, ilegal ou perturbador é proibido. Evite linguagem tóxica.</p>
                        <p><strong>3. Spam & Publicidade:</strong> Sem spam de mensagens, reações ou links. Anúncios externos precisam de aprovação da staff.</p>
                        <p><strong>4. Segurança & Privacidade:</strong> Nunca compartilhe dados pessoais. Golpes, phishing ou atividade maliciosa levam a bans.</p>
                        <p><strong>5. Decisões da Staff:</strong> Respeite a staff e suas decisões. Apresente apelos calmamente.</p>
                        <p><strong>6. Uso de Canais:</strong> Use canais para seu propósito pretendido. Leia pins e descrições.</p>
                        <button onclick="translateModal()">🌐 Translate to English</button>
                        <form action="/login" method="get">
                            <button type="submit">Entrar com Discord</button>
                        </form>
                    `;
                } else {
                    modalContent.innerHTML = `
                        <p>Welcome to <strong>Syntax's Back</strong>! To ensure a safe and bot-free community, we use <strong>OAuth2 verification</strong>.</p>
                        <p>This process authorizes your Discord account securely and adds you to the server automatically.</p>
                        <p><strong>Verification Steps:</strong></p>
                        <ol>
                            <li>Read the detailed rules below.</li>
                            <li>Click 'Sign In with Discord'.</li>
                            <li>Authorize the app in the popup.</li>
                            <li>You will be added to the server and verified instantly.</li>
                        </ol>
                        <p><strong>Why verify?</strong></p>
                        <ul>
                            <li>Prevents bots and spam accounts.</li>
                            <li>Ensures only real users join.</li>
                            <li>Protects our community from raids and abuse.</li>
                            <li>Uses Discord's official OAuth2 for security.</li>
                        </ul>
                        <p><strong>Benefits after verification:</strong></p>
                        <ul>
                            <li>Full access to all channels.</li>
                            <li>Participate in chats, events, and giveaways.</li>
                            <li>Gain XP and level up by chatting.</li>
                            <li>Use slash commands like /suggestion and /level.</li>
                            <li>Enjoy our beautiful lilac/purple theme.</li>
                        </ul>
                        <p><strong>Detailed Rules Summary:</strong></p>
                        <p><strong>1. Respect & Behavior:</strong> No insults, harassment, hate speech, or discrimination. Keep discussions civil.</p>
                        <p><strong>2. Content Policy:</strong> NSFW, illegal, or disturbing content is forbidden. Avoid toxic language.</p>
                        <p><strong>3. Spam & Advertising:</strong> No spamming messages, reactions, or links. External ads require staff approval.</p>
                        <p><strong>4. Security & Privacy:</strong> Never share personal data. Scams, phishing, or malicious activity leads to bans.</p>
                        <p><strong>5. Staff Decisions:</strong> Respect staff and their decisions. Appeal punishments calmly.</p>
                        <p><strong>6. Channel Usage:</strong> Use channels for their intended purpose. Read pins and descriptions.</p>
                        <button onclick="translateModal()">🌐 Translate to Portuguese</button>
                        <form action="/login" method="get">
                            <button type="submit">Sign In with Discord</button>
                        </form>
                    `;
                }
            }
            window.onclick = function(event) {
                if (event.target == document.getElementById('signInModal')) {
                    closeModal();
                }
            }
        </script>
    </body>
    </html>
    ''', user=user)

@app.route('/login')
def oauth_login():
    discord_auth_url = (
        f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify%20guilds.join"
    )
    return redirect(discord_auth_url)

@app.route('/callback')
def oauth_callback():
    code = request.args.get('code')
    if not code:
        return "Error: No code provided", 400

    token_response = auth_handler.exchange_code(code)
    access_token = token_response.get('access_token')
    if not access_token:
        return "Error: Failed to get access token", 400

    # Get user info
    user_response = requests.get('https://discord.com/api/v10/users/@me', headers={'Authorization': f'Bearer {access_token}'})
    user_data = user_response.json()
    user_id = user_data['id']

    # Add user to guilds
    for guild in GUILDS_TO_ADD:
        result = auth_handler.add_member_to_guild(user_id, access_token, guild['guild_id'], guild['role_id'])
        if result.status_code not in [201, 204]:
            print(f"Failed to add user to guild {guild['guild_id']}: {result.text}")

    # Store user in session
    session['user'] = user_data

    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Verification Successful</title>
        <style>
            body { font-family: Arial, sans-serif; background: linear-gradient(135deg, #9b59b6, #71368a); color: white; text-align: center; padding: 50px; }
            .container { max-width: 600px; margin: auto; background: rgba(0,0,0,0.5); padding: 20px; border-radius: 10px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Verification Successful!</h1>
            <p>You have been verified and added to the servers. You can now close this window and return to Discord.</p>
            <a href="/">Go to Home</a>
        </div>
    </body>
    </html>
    ''')

@app.route('/account')
def account():
    user = session.get('user')
    if not user:
        return redirect('/login')
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="pt">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Syntax's Back - Conta</title>
        <style>
            body { font-family: Arial, sans-serif; background: linear-gradient(135deg, #9b59b6, #71368a); color: white; margin: 0; padding: 0; }
            header { display: flex; justify-content: space-between; align-items: center; padding: 20px; background: rgba(0,0,0,0.5); }
            .logo { font-size: 24px; font-weight: bold; }
            .nav { display: flex; gap: 20px; }
            .nav a { color: white; text-decoration: none; }
            .sign-in-btn { background: #e91e63; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }
            .container { max-width: 600px; margin: 50px auto; background: rgba(0,0,0,0.5); padding: 20px; border-radius: 10px; text-align: center; }
            .modal { display: none; position: fixed; z-index: 1; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.4); }
            .modal-content { background-color: #fefefe; margin: 15% auto; padding: 20px; border: 1px solid #888; width: 80%; max-width: 400px; border-radius: 10px; }
            .close { color: #aaa; float: right; font-size: 28px; font-weight: bold; cursor: pointer; }
            .close:hover { color: black; }
            form { display: flex; flex-direction: column; }
            input { margin-bottom: 10px; padding: 10px; border: 1px solid #ccc; border-radius: 5px; }
            button { background: #9b59b6; color: white; padding: 10px; border: none; border-radius: 5px; cursor: pointer; }
        </style>
    </head>
    <body>
        <header>
            <div class="logo">Syntax's Back</div>
            <nav class="nav">
                <a href="/">Início</a>
                <a href="/account">Conta</a>
                {% if user %}
                    <a href="/logout">Sair</a>
                {% else %}
                    <button class="sign-in-btn" onclick="openModal()">Entrar</button>
                {% endif %}
            </nav>
        </header>
        <div class="container">
            <h1>Sua Conta</h1>
            <p>Nome de usuário: {{ user.username }}#{{ user.discriminator }}</p>
            <p>ID: {{ user.id }}</p>
            <img src="https://cdn.discordapp.com/avatars/{{ user.id }}/{{ user.avatar }}.png" alt="Avatar" style="border-radius: 50%; width: 100px;">
        </div>
        <div id="signInModal" class="modal">
            <div class="modal-content">
                <span class="close" onclick="closeModal()">&times;</span>
                <h2>Entrar / Registrar</h2>
                <form action="/login" method="get">
                    <button type="submit">Entrar com Discord</button>
                </form>
            </div>
        </div>
        <script>
            function openModal() {
                document.getElementById('signInModal').style.display = 'block';
            }
            function closeModal() {
                document.getElementById('signInModal').style.display = 'none';
            }
            window.onclick = function(event) {
                if (event.target == document.getElementById('signInModal')) {
                    closeModal();
                }
            }
        </script>
    </body>
    </html>
    ''', user=user)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
