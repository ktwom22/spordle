import pandas as pd
import random
import re
import os
import json
import uuid
from flask import Flask, render_template, request, session, redirect, url_for, jsonify, flash
from flask_session import Session
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from datetime import date, timedelta
from collections import defaultdict

app = Flask(__name__)

app.secret_key = os.environ.get('SECRET_KEY', 'supersecretkey')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = './flask_session/'
app.config['SESSION_PERMANENT'] = False
Session(app)

# ------ User Auth Setup ------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

USERS_FILE = "users.json"

def load_users():
    try:
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

class User(UserMixin):
    def __init__(self, username):
        self.id = username

@login_manager.user_loader
def load_user(user_id):
    users = load_users()
    if user_id in users:
        return User(user_id)
    return None

STATS_FILE = "game_stats.json"

def save_user_result(username, time_elapsed, guesses, day):
    print(f"Writing stat: username={username}, time_elapsed={time_elapsed}, guesses={guesses}, day={day}")
    try:
        with open(STATS_FILE, "r") as f:
            all_stats = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        all_stats = {}
    if day not in all_stats:
        all_stats[day] = []
    all_stats[day].append({
        "username": username,
        "time": time_elapsed,
        "guesses": guesses,
        "day": day
    })
    with open(STATS_FILE, "w") as f:
        json.dump(all_stats, f)
    print("Stat successfully written!")

def get_stats_for_period(period='day'):
    try:
        with open(STATS_FILE, "r") as f:
            all_stats = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        all_stats = {}

    if period == 'week':
        today = date.today()
        last7 = [(today - timedelta(days=i)).isoformat() for i in range(7)]
        stats = []
        for d in last7:
            stats.extend(all_stats.get(d, []))
        return stats
    else:
        today_str = date.today().isoformat()
        return all_stats.get(today_str, [])

def calculate_leaderboard(stats_list, period='day'):
    users = load_users()  # Only registered users
    user_stats = defaultdict(list)
    for entry in stats_list:
        if entry['username'] not in users:
            continue
        user_stats[entry['username']].append(entry)
    leaderboard = []
    if period == 'week':
        for username, games in user_stats.items():
            days = {}
            for g in games:
                day_key = g.get('day','')
                score = g['guesses'] + g['time']
                if day_key and (day_key not in days or score < days[day_key]):
                    days[day_key] = score
            if len(days) < 5:
                continue
            total_score = sum(days.values())
            leaderboard.append({
                'username': username,
                'days_played': len(days),
                'total_score': total_score,
                'avg_score': total_score / len(days) if len(days) > 0 else float('inf')
            })
        leaderboard.sort(key=lambda x: (x['total_score'], x['username']))
    else:
        for username, games in user_stats.items():
            best = min(games, key=lambda g: g['guesses'] + g['time'])
            leaderboard.append({
                'username': username,
                'score': best['guesses'] + best['time'],
                'guesses': best['guesses'],
                'time': best['time']
            })
        leaderboard.sort(key=lambda x: (x['score'], x['username']))
    return leaderboard

df = pd.read_csv("NBA_player_info_and_stats_joined_clean.csv")

def parse_salary(s):
    try:
        return int(re.sub(r'[^\d]', '', str(s)))
    except:
        return 0

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

def get_daily_player():
    today_index = date.today().toordinal() % len(players)
    return players[today_index]

@app.before_request
def ensure_username_and_login_prompt():
    if not current_user.is_authenticated and "username" not in session:
        session["username"] = str(uuid.uuid4())
    # Tracking: reset prompt counter once per day
    today_str = date.today().isoformat()
    if session.get('last_prompt_date') != today_str:
        session['prompt_declined_count'] = 0
        session['last_prompt_date'] = today_str
        session['show_login_prompt'] = True
    session.setdefault('show_login_prompt', True)

@app.route('/decline_login_prompt', methods=['POST'])
def decline_login_prompt():
    session['show_login_prompt'] = False
    session['prompt_declined_count'] = session.get('prompt_declined_count', 0) + 1
    session.modified = True
    return '', 204

@app.route('/login', methods=['GET', 'POST'])
def login():
    users = load_users()
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        # Registration
        if request.form.get("register"):
            if username in users:
                flash("Username already taken.", "error")
            else:
                users[username] = {"password": password}
                save_users(users)
                login_user(User(username))
                flash("Registered and logged in successfully.", "success")
                flash("event:register", "ga_event")
                return redirect(request.args.get("next") or url_for("index"))
        # Login
        else:
            if username in users and users[username]["password"] == password:
                login_user(User(username))
                flash("Logged in successfully.", "success")
                flash("event:login", "ga_event")
                return redirect(request.args.get("next") or url_for("index"))
            flash("Invalid credentials", "error")
    return render_template("login.html")

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Logged out.", "success")
    flash("event:logout", "ga_event")
    return redirect(url_for("index"))

@app.route('/', methods=['GET', 'POST'])
def index():
    today_str = date.today().isoformat()

    if session.get('last_played_date') != today_str:
        session['target_player'] = get_daily_player()
        session['guesses'] = []
        session['hint_used'] = False
        session['last_played_date'] = today_str
        session['game_over'] = False
        session['time_elapsed'] = 0
        session['result_saved'] = None

    error = None
    max_reached = False
    won = False

    guesses = session.get('guesses', [])
    target = session['target_player']

    if guesses:
        for g in guesses:
            if g['name'] == target['name']:
                won = True
                session['game_over'] = True
                break
    if len(guesses) >= MAX_GUESSES or won:
        max_reached = True
        session['game_over'] = True

    if request.method == 'POST' and not session.get('game_over', False):
        guess_name = request.form['guess']
        normalized_guess = normalize_name(guess_name)
        guess_player = next((p for p in players if normalize_name(p['name']) == normalized_guess), None)

        if guess_player:
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
            if guess_player['name'] == target['name']:
                won = True
                max_reached = True
                session['game_over'] = True
        else:
            error = "Player not found! Please check spelling."

    guesses = session.get('guesses', [])
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
        won=won,
        target_player=session['target_player'],
        error=error,
        MAX_GUESSES=MAX_GUESSES
    )

@app.route('/set_time_elapsed', methods=['POST'])
def set_time_elapsed():
    print("---- /set_time_elapsed CALLED ----")
    print("Raw data:", request.data)
    try:
        print("Request JSON:", request.json)
    except Exception as e:
        print("JSON parse error:", str(e))
    elapsed = request.json.get('time_elapsed', 0) if request.json else 0
    print("Elapsed received:", elapsed)
    print("Session BEFORE:", dict(session))

    session['time_elapsed'] = elapsed
    session.modified = True

    today_str = date.today().isoformat()
    max_reached = session.get("game_over", False)
    result_saved = session.get("result_saved")
    guesses = session.get("guesses", [])
    username = current_user.get_id() if current_user.is_authenticated else session.get("username", "anon")

    print("max_reached:", max_reached, "result_saved:", result_saved, "username:", username)

    if max_reached and result_saved != today_str and elapsed > 0:
        print("Saving user result!")
        save_user_result(
            username=username,
            time_elapsed=elapsed,
            guesses=len(guesses),
            day=today_str
        )
        session["result_saved"] = today_str
    else:
        print("NOT saving user result (conditions not met)")

    print("Session AFTER:", dict(session))
    print("---- /set_time_elapsed END ----")
    return jsonify(success=True)

@app.route('/reset')
def reset():
    session.pop('target_player', None)
    session.pop('guesses', None)
    session.pop('game_over', None)
    session.pop('last_played_date', None)
    session.pop('time_elapsed', None)
    session.pop('result_saved', None)
    return redirect(url_for('index'))

@app.route('/player_names')
def player_names():
    return jsonify([p['name'] for p in players])

@app.route('/stats')
@login_required
def stats():
    period = request.args.get("period", "day")
    stats_list = get_stats_for_period(period)
    user = current_user.get_id()
    user_result = next((x for x in stats_list if x["username"] == user), None)
    session_time = session.get('time_elapsed', 0)
    session_guesses = len(session.get("guesses", []))
    if (not user_result or user_result["time"] == 0) and session_time > 0:
        user_result = {
            "username": user,
            "time": session_time,
            "guesses": session_guesses
        }
    leaderboard = calculate_leaderboard(stats_list, period)
    return render_template(
        "stats.html",
        stats_list=stats_list,
        user_result=user_result,
        period=period,
        leaderboard=leaderboard
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)