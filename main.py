import pandas as pd
import random
import re
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from flask_session import Session
from datetime import date
import os

app = Flask(__name__)

# Use a fixed secret key (can also be set via environment variable)
app.secret_key = os.environ.get('SECRET_KEY', 'supersecretkey')

# Configure server-side sessions
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = './flask_session/'
app.config['SESSION_PERMANENT'] = False
Session(app)

# Load player data
df = pd.read_csv("NBA_player_info_and_stats_joined_clean.csv")

def parse_salary(s):
    try:
        return int(re.sub(r'[^\d]', '', str(s)))
    except:
        return 0

# Only keep salaries above 15MM
df = df[df['Salary'].apply(parse_salary) > 15_000_000].reset_index(drop=True)

def normalize_name(name):
    return re.sub(r'\W+', '', str(name)).lower().strip()

def split_name_and_jersey(name):
    m = re.match(r'^(.*?)(\d+)$', str(name).strip())
    if m:
        return m.group(1).strip(), m.group(2)
    else:
        return name.strip(), ''

df[['PlayerName', 'Jersey']] = df['Name'].apply(lambda x: pd.Series(split_name_and_jersey(x)))
player_name_col = 'PlayerName'

# Remove 'HT' and 'College' from attributes
ATTRIBUTES = ['Jersey', 'Team', 'POS', 'Age', 'Salary']
MAX_GUESSES = 8

def is_numeric(val):
    try:
        float(val)
        return True
    except:
        return False

def is_close(guess, answer):
    if not is_numeric(guess) or not is_numeric(answer):
        return False
    guess, answer = float(guess), float(answer)
    if abs(guess - answer) <= 1:
        return True
    if answer == 0:
        return False
    return abs(guess - answer) / abs(answer) <= 0.1

def get_arrow(guess, answer):
    if not is_numeric(guess) or not is_numeric(answer):
        return ""
    guess, answer = float(guess), float(answer)
    if guess < answer:
        return "↑"
    elif guess > answer:
        return "↓"
    else:
        return ""

players = []
for _, row in df.iterrows():
    players.append({
        'name': str(row.get(player_name_col, '')).strip(),
        **{attr: str(row.get(attr, '')) for attr in ATTRIBUTES}
    })

# Daily player selection
def get_daily_player():
    today_index = date.today().toordinal() % len(players)
    return players[today_index]

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'target_player' not in session:
        session['target_player'] = get_daily_player()
        session['guesses'] = []
        session['hint_used'] = False

    error = None
    max_reached = False

    if request.method == 'POST':
        guess_name = request.form['guess']
        normalized_guess = normalize_name(guess_name)
        guess_player = next((p for p in players if normalize_name(p['name']) == normalized_guess), None)

        if guess_player:
            target = session['target_player']
            result = {}
            for attr in ATTRIBUTES:
                g_val, t_val = guess_player.get(attr, ''), target.get(attr, '')
                if g_val == t_val:
                    result[attr] = ('correct', g_val, "")
                elif is_numeric(g_val) and is_numeric(t_val) and is_close(g_val, t_val):
                    arrow = get_arrow(g_val, t_val)
                    result[attr] = ('close', g_val, arrow)
                elif is_numeric(g_val) and is_numeric(t_val):
                    arrow = get_arrow(g_val, t_val)
                    result[attr] = ('off', g_val, arrow)
                else:
                    result[attr] = ('off', g_val, "")
            session['guesses'].append({'name': guess_player['name'], 'result': result})
            session.modified = True
        else:
            error = "Player not found! Please check spelling."

    guesses = session.get('guesses', [])
    if len(guesses) >= MAX_GUESSES:
        max_reached = True

    # Create emoji grid
    emoji_grid = []
    for g in guesses:
        row = ""
        for attr in ATTRIBUTES:
            status, _, _ = g['result'][attr]
            if status == 'correct':
                row += "🟩"
            elif status == 'close':
                row += "🟨"
            else:
                row += "⬜"
        emoji_grid.append(row)

    # Stats
    stats = {
        'guesses': len(guesses),
        'time_elapsed': session.get('time_elapsed', 0)
    }

    return render_template(
        'index.html',
        player_list=[p['name'] for p in players],
        guesses=guesses,
        attributes=ATTRIBUTES,
        emoji_grid=emoji_grid,
        stats=stats,
        max_reached=max_reached,
        target_player=session['target_player'],
        error=error
    )

@app.route('/reset')
def reset():
    session.pop('target_player', None)
    session.pop('guesses', None)
    return redirect(url_for('index'))

@app.route('/player_names')
def player_names():
    return jsonify([p['name'] for p in players])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
