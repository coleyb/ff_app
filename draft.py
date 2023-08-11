# This script takes the FantasyPros endpoint and converts it to a CSV file
# then allows you to determine the best available draft pick based on the rest available

import pandas as pd
import requests
import csv
from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
import streamlit as st
import math

draft_position = 0

# Fetch the JSON data
url = "https://api.sportsdata.io/v3/nfl/stats/json/FantasyPlayers?key=3a518244587549ae819c8257e4d51930"
response = requests.get(url)
data = response.json()

csv_path = "./fantasy_players.csv"

@st.cache_resource
def load_fantasy_data():
    """Load the fantasy players data from a URL endpoint, add required columns, and save to CSV."""
    # Fetch the JSON data
    response = requests.get(url)
    data = response.json()

    # Convert JSON to DataFrame
    df = pd.DataFrame(data)
    
    # Add required columns
    df['is_drafted'] = 0
    df['draft_order'] = ''
    df['my_team'] = False
    
    # Sort the DataFrame
    df = df.sort_values(by='ProjectedFantasyPoints', ascending=False)

    # Save to CSV
    df.to_csv(csv_path, index=False)
    
    return df

# Use the function to load the data
fantasy_data = load_fantasy_data()


def get_next_best_available(data, position):
    """Get the next best available player based on the is_drafted column and specified position."""
    # Filter out drafted players using the is_drafted column and filter by position
    available_players = data[(data['is_drafted'] == False) & (data['Position'] == position)]
    
    # If no available players for the specified position, return None
    if available_players.empty:
        return None
    
    # Sort players by AverageDraftPositionPPR and then by ProjectedFantasyPoints
    sorted_players = available_players.sort_values(by=['AverageDraftPositionPPR', 'ProjectedFantasyPoints'], ascending=[True, False])
    
    # Return the top available player
    return sorted_players.iloc[0]

def set_draft_status(df, player_name, drafted, to_my_team=False, my_draft_position=None, num_users=None):
    player_index = df[df['Name'] == player_name].index[0]
    df.at[player_index, 'is_drafted'] = drafted
    
    if drafted:
        max_order = df['draft_order'].max()
        next_order = 1 if pd.isna(max_order) else int(max_order) + 1
        df.at[player_index, 'draft_order'] = next_order
        
        # Check if the player should be on "my team"
        current_pick = int(next_order)
        if to_my_team or (current_pick % num_users == my_draft_position):
            df.at[player_index, 'my_team'] = True
    else:
        df.at[player_index, 'draft_order'] = None
        df.at[player_index, 'my_team'] = False

def get_my_team(df):
    """Returns the user's team from the DataFrame."""
    return df[df['my_team'] == True]

def get_roster_constraints(my_team):
    """Returns the remaining roster constraints based on the user's team."""
    roster_constraints = {
        'QB': 1,
        'WR': 2,
        'RB': 2,
        'TE': 1,
        'FLEX': 1,
        'DST': 1,
        'K': 1
    }

    for position in ['QB', 'WR', 'RB', 'TE', 'DST', 'K']:
        roster_constraints[position] -= len(my_team[my_team['Position'] == position])

    return roster_constraints

def update_roster_constraints_for_flex(my_team, roster_constraints):
    """Updates the roster constraints considering the flex position."""
    if roster_constraints['FLEX'] > 0:
        potential_flex = my_team[(my_team['Position'] == 'WR') | 
                                (my_team['Position'] == 'RB') | 
                                (my_team['Position'] == 'TE')]
        if len(potential_flex) < 3:  # 2 WRs + 1 RB or 2 RBs + 1 WR would fill the Flex
            roster_constraints['TE'] -= len(potential_flex)
    return roster_constraints

def get_picks_before_your_turn(df, my_draft_position, num_users):
    """Returns the number of picks before the user's turn."""
    total_drafted_players = df[df['is_drafted'] == True].shape[0]
    current_round = (total_drafted_players // num_users) + 1

    if current_round % 2 == 1:  # Odd rounds
        return my_draft_position - (total_drafted_players % num_users)
    else:  # Even rounds
        return num_users - (total_drafted_players % num_users) + my_draft_position
    
def suggest_pick(df, my_draft_position, num_users):
    # If we have a current suggested player and he's still undrafted, suggest him again
    if 'suggested_player_name' in st.session_state and st.session_state.suggested_player_name in df['Name'].values and not df[df['Name'] == st.session_state.suggested_player_name].iloc[0]['is_drafted']:
        return df[df['Name'] == st.session_state.suggested_player_name].iloc[0]

    # Get user's team and the remaining roster constraints
    my_team = get_my_team(df)
    roster_constraints = get_roster_constraints(my_team)
    roster_constraints = update_roster_constraints_for_flex(my_team, roster_constraints)

    picks_before_your_turn = get_picks_before_your_turn(df, my_draft_position, num_users)

    st.markdown(f"Picks to go: {picks_before_your_turn}", unsafe_allow_html=True)

    # Normalize ProjectedFantasyPoints and AverageDraftPositionPPR
    df['NormalizedPoints'] = (df['ProjectedFantasyPoints'] - df['ProjectedFantasyPoints'].min()) / (df['ProjectedFantasyPoints'].max() - df['ProjectedFantasyPoints'].min())
    df['NormalizedADP'] = 1 - (df['AverageDraftPositionPPR'] - df['AverageDraftPositionPPR'].min()) / (df['AverageDraftPositionPPR'].max() - df['AverageDraftPositionPPR'].min())

    # Combine the normalized scores
    weight_points = 2
    weight_adp = 1
    df['CombinedScore'] = weight_points * df['NormalizedPoints'] - weight_adp * df['NormalizedADP']

    # Get undrafted players sorted by combined score
    undrafted_players = df[df['is_drafted'] == False].sort_values(by='CombinedScore', ascending=False).reset_index(drop=True)

    # Start at the player projected to go around your draft position and check for the first player that fills an immediate need
    starting_index = my_draft_position - 1
    for index in range(starting_index, len(undrafted_players)):
        player = undrafted_players.iloc[index]
        position = player['Position']
        if roster_constraints[position] > 0:  # This player fills a need
            return player
        if position in ['WR', 'RB', 'TE'] and roster_constraints['FLEX'] > 0:  # This player can be used in a FLEX position
            return player

    return None  # In case all positions are filled

# Streamlit
def main():
    st.title("Fantasy Football Draft Assistant")

    num_users = st.number_input('Enter the number of users in the draft:', min_value=2, value=10)
    my_draft_position = st.number_input('Enter your draft position:', min_value=1, max_value=num_users, value=1)

    # Initialize or update the previous_draft_position in session_state
    if 'previous_draft_position' not in st.session_state:
        st.session_state.previous_draft_position = my_draft_position
    else:
        if st.session_state.previous_draft_position != my_draft_position:
            if 'suggested_player_name' in st.session_state:
                del st.session_state.suggested_player_name
            st.session_state.previous_draft_position = my_draft_position

    # Load data
    fantasy_data = load_fantasy_data()

    # Filter data based on search query and exclude already drafted players
    search_query = st.text_input("Search by player or position:")
    filtered_data = fantasy_data[
        (fantasy_data['Name'].str.contains(search_query, case=False) | fantasy_data['Position'].str.contains(search_query, case=False))
        & (fantasy_data['is_drafted'] == False)
    ]

    # Sort by ProjectedFantasyPoints and get the top 20 players
    top_20_players = filtered_data.sort_values(by='AverageDraftPositionPPR', ascending=True).head(20)

    # Display drafted players in a separate table, sorted by draft order
    fantasy_data['draft_order'] = pd.to_numeric(fantasy_data['draft_order'], errors='coerce')
    drafted_players = fantasy_data[fantasy_data['is_drafted'] == True].sort_values(by='draft_order')

    if not drafted_players.empty:
        st.subheader("Drafted Players")
        
        # Modify display of drafted players based on 'my_team' flag
        drafted_players['Display'] = drafted_players.apply(
            lambda row: f"{row['Name']} - {row['Position']}{' *' if row['my_team'] else ''}",
            axis=1
        )
        
        # Display only the modified 'Display' column
        st.table(drafted_players['Display'])

    # Get the suggested pick
    if 'suggested_player_name' not in st.session_state:
        next_suggested_player = suggest_pick(fantasy_data, my_draft_position, num_users)
        st.session_state.suggested_player_name = next_suggested_player['Name']
    else:
        next_suggested_player = fantasy_data[fantasy_data['Name'] == st.session_state.suggested_player_name].iloc[0]
    
    st.markdown(f"**Next Suggested Pick:** {next_suggested_player['Name']} - {next_suggested_player['Position']} - {next_suggested_player['ProjectedFantasyPoints']} points - {next_suggested_player['AverageDraftPositionPPR']} ADP - {next_suggested_player['ByeWeek']} bye", unsafe_allow_html=True)

    # Display the top 20 filtered results with draft buttons
    for index, row in top_20_players.iterrows():
        col1, col2, col3 = st.columns(3)

        # Check if player is the suggested player
        player_name = row['Name']
        player_details = f"{player_name} - {row['Position']} - {row['ProjectedFantasyPoints']} points - {row['AverageDraftPositionPPR']} ADP - {row['ByeWeek']} bye"
        
        if player_name == st.session_state.suggested_player_name:
            player_display = f"**<span style='color:red;'>{player_details}</span>**"
            with col1:
                st.markdown(player_display, unsafe_allow_html=True)
        else:
            with col1:
                st.write(player_details)

        with col2:
            # Add a draft button for each player
            draft_button = st.button(f"Draft {player_name}", key=row['Name'])
            # When the "Draft" button is clicked:
        if draft_button:
            set_draft_status(fantasy_data, row['Name'], True, my_draft_position=my_draft_position, num_users=num_users)
            fantasy_data.to_csv(csv_path, index=False)
            # Update the suggested pick
            next_suggested_player = suggest_pick(fantasy_data, my_draft_position, num_users)
            st.experimental_rerun()  # Rerun the app to update the suggested pick
        
        with col3:
            # Add a "Draft to My Team" button for each player
            my_team_button = st.button(f"Draft {row['Name']} to My Team", key=f"MyTeam_{row['Name']}")
            if my_team_button:
                set_draft_status(fantasy_data, row['Name'], True, to_my_team=True, my_draft_position=my_draft_position, num_users=num_users)
                fantasy_data.to_csv(csv_path, index=False)
                st.write(f"{row['Name']} has been drafted to your team!")
                # Remove the suggested player if he's drafted
                if row['Name'] == st.session_state.suggested_player_name:
                    del st.session_state.suggested_player_name

if __name__ == "__main__":
    main()
