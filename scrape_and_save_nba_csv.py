import re
import urllib.request
from time import sleep
import pandas as pd

def build_team_urls():
    with urllib.request.urlopen('https://www.espn.com/nba/teams') as f:
        teams_source = f.read().decode('utf-8')
    teams = dict(re.findall(r"www\.espn\.com/nba/team/_/name/(\w+)/(.+?)\"", teams_source))
    roster_urls = []
    for key in teams.keys():
        roster_urls.append('https://www.espn.com/nba/team/roster/_/name/' + key + '/' + teams[key])
        teams[key] = str(teams[key])
    return dict(zip(teams.values(), roster_urls))

def get_player_info(roster_url):
    sleep(0.5)
    try:
        tables = pd.read_html(roster_url)
        df = tables[0]
        df['TeamURL'] = roster_url
        return df
    except Exception as e:
        print(f"Failed to parse {roster_url}: {e}")
        return pd.DataFrame()

def get_all_players_df():
    # Static mapping of teams to divisions and conferences
    division_map = {
        "boston-celtics": ("Atlantic", "Eastern"),
        "brooklyn-nets": ("Atlantic", "Eastern"),
        "new-york-knicks": ("Atlantic", "Eastern"),
        "philadelphia-76ers": ("Atlantic", "Eastern"),
        "toronto-raptors": ("Atlantic", "Eastern"),
        "chicago-bulls": ("Central", "Eastern"),
        "cleveland-cavaliers": ("Central", "Eastern"),
        "detroit-pistons": ("Central", "Eastern"),
        "indiana-pacers": ("Central", "Eastern"),
        "milwaukee-bucks": ("Central", "Eastern"),
        "atlanta-hawks": ("Southeast", "Eastern"),
        "charlotte-hornets": ("Southeast", "Eastern"),
        "miami-heat": ("Southeast", "Eastern"),
        "orlando-magic": ("Southeast", "Eastern"),
        "washington-wizards": ("Southeast", "Eastern"),
        "denver-nuggets": ("Northwest", "Western"),
        "minnesota-timberwolves": ("Northwest", "Western"),
        "oklahoma-city-thunder": ("Northwest", "Western"),
        "portland-trail-blazers": ("Northwest", "Western"),
        "utah-jazz": ("Northwest", "Western"),
        "golden-state-warriors": ("Pacific", "Western"),
        "los-angeles-clippers": ("Pacific", "Western"),
        "los-angeles-lakers": ("Pacific", "Western"),
        "phoenix-suns": ("Pacific", "Western"),
        "sacramento-kings": ("Pacific", "Western"),
        "dallas-mavericks": ("Southwest", "Western"),
        "houston-rockets": ("Southwest", "Western"),
        "memphis-grizzlies": ("Southwest", "Western"),
        "new-orleans-pelicans": ("Southwest", "Western"),
        "san-antonio-spurs": ("Southwest", "Western")
    }

    rosters = build_team_urls()
    all_players_df = pd.DataFrame()

    for team, team_url in rosters.items():
        print("Gathering player info for team:", team)
        team_df = get_player_info(team_url)
        team_df['Team'] = team

        # Add division & conference info
        division, conference = division_map.get(team, ("Unknown", "Unknown"))
        team_df['Division'] = division
        team_df['Conference'] = conference

        all_players_df = pd.concat([all_players_df, team_df], ignore_index=True)

    return all_players_df

def main():
    all_players_df = get_all_players_df()
    all_players_df.to_csv("NBA_player_info_with_division_conf.csv", index=False)
    print("Saved NBA_player_info_with_division_conf.csv with shape", all_players_df.shape)

if __name__ == '__main__':
    main()
