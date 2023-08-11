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

# Open a CSV file for writing
with open(csv_path, 'w', newline='') as csvfile:
    # Add 'is_drafted' to the list of fieldnames
    fieldnames = list(data[0].keys()) + ['is_drafted']
    
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

    writer.writeheader()
    for row in data:
        # Set the 'is_drafted' value to 0 for each row
        row['is_drafted'] = 0
        writer.writerow(row)


@st.cache_resource
def load_fantasy_data(csv_path):
    """Load the fantasy players data from a CSV."""
    # Step 1: Read the CSV into a pandas DataFrame
    df = pd.read_csv(csv_path)

    # Step 2: Add a new column to the DataFrame
    df['is_drafted'] = 0
    df['draft_order'] = ''
    df = df.sort_values(by='ProjectedFantasyPoints', ascending=False)

    # Step 3: Write the DataFrame back to the CSV
    df.to_csv(csv_path, index=False)
    return pd.read_csv(csv_path)

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

def set_draft_status(df, player_name, is_drafted=True):
    """Set the draft status of a player."""
    player_index = df[df['Name'] == player_name].index[0]
    df.at[player_index, 'is_drafted'] = is_drafted
    
    if is_drafted:
        # If the player is being drafted, set their draft order
        max_order = df['draft_order'].max()
        next_order = 1 if pd.isna(max_order) else max_order + 1
        df.at[player_index, 'draft_order'] = next_order

# Streamlit
def main():
    st.title("Fantasy Football Draft Assistant")

    num_users = st.number_input('Enter the number of users in the draft:', min_value=2, value=10)
    my_draft_position = st.number_input('Enter your draft position:', min_value=1, max_value=num_users, value=1)

    # Load data
    fantasy_data = load_fantasy_data(csv_path)

    # Calculate the current draft round for your team
    total_drafted_players = fantasy_data[fantasy_data['is_drafted'] == True].shape[0]
    current_round = math.ceil((total_drafted_players + 1) / num_users)

    # Create an input box for search
    search_query = st.text_input("Search by player or position:")

    # Filter data based on search query and exclude already drafted players
    filtered_data = fantasy_data[
        (fantasy_data['Name'].str.contains(search_query, case=False) | fantasy_data['Position'].str.contains(search_query, case=False))
        & (fantasy_data['is_drafted'] == False)
    ]

    # Sort by ProjectedFantasyPoints and get the top 20 players
    top_20_players = filtered_data.sort_values(by='ProjectedFantasyPoints', ascending=False).head(20)

    # Display drafted players in a separate table, sorted by draft order
    drafted_players = fantasy_data[fantasy_data['is_drafted'] == True].sort_values(by='draft_order')

    if not drafted_players.empty:
        st.subheader("Drafted Players")
        
        # Modify display of drafted players based on 'my_team' flag
        drafted_players['Display'] = drafted_players.apply(
            lambda row: f"{row['Name']} - {row['Position']}",
            axis=1
        )
        
        # Display only the modified 'Display' column
        st.table(drafted_players['Display'])


    # Calculate upcoming draft turns based on your position and the snake draft pattern
    def calculate_draft_turns(my_position, num_teams, num_rounds=10):
        turns = []
        for round_num in range(1, num_rounds + 1):
            if round_num % 2 == 1:  # Odd rounds
                turn = (round_num - 1) * num_teams + my_position
            else:  # Even rounds (snake draft)
                turn = round_num * num_teams - (my_position - 1)
            turns.append(turn)
        return turns

    upcoming_turns = calculate_draft_turns(my_draft_position, num_users)

    def suggest_pick(df, draft_position, num_teams):
        total_drafted_players = df[df['is_drafted'] == True].shape[0]
        current_round = (total_drafted_players // num_teams) + 1

        # Determine pick number in the current round
        if current_round % 2 == 1:  # Odd rounds
            pick_in_round = total_drafted_players % num_teams + 1
        else:  # Even rounds
            pick_in_round = num_teams - (total_drafted_players % num_teams)

        # Number of picks before your turn
        if current_round % 2 == 1:  # Odd rounds
            picks_before_your_turn = draft_position - pick_in_round
        else:  # Even rounds
            picks_before_your_turn = pick_in_round - draft_position

        undrafted_players = df[df['is_drafted'] == False]

        # If all players have been drafted, return None
        if undrafted_players.empty:
            return None

        # Suggest a player
        suggested_index = min(picks_before_your_turn, len(undrafted_players) - 1)
        suggested_player = undrafted_players.sort_values(by='ProjectedFantasyPoints', ascending=False).iloc[suggested_index]
        return suggested_player



    # Suggest players for each upcoming turn
    suggestions = {}
    for turn in upcoming_turns:
        available_players = fantasy_data[(fantasy_data['is_drafted'] == False)].sort_values(by='ProjectedFantasyPoints', ascending=False)
        # Check if there are still players available
        if not available_players.empty:
            # Suggest the highest projected player who is still available around that turn
            suggested_player = available_players.iloc[min(turn, len(available_players) - 1)]
            suggestions[turn] = suggested_player['Name']

    next_suggested_player = suggest_pick(fantasy_data, my_draft_position, num_users)

    
    # Initialize session state variable for drafted player name
    if 'drafted_name' not in st.session_state:
        st.session_state.drafted_name = None

    # Get the suggested pick
    next_suggested_player = suggest_pick(fantasy_data, my_draft_position, num_users)
    if next_suggested_player is not None:
        st.markdown(f"**Next Suggested Pick:** {next_suggested_player['Name']} - {next_suggested_player['Position']} - {next_suggested_player['ProjectedFantasyPoints']} points - {next_suggested_player['AverageDraftPositionPPR']} ADP - {next_suggested_player['ByeWeek']} bye", unsafe_allow_html=True)
    else:
        st.write("All players have been drafted.")


    # Display the top 20 filtered results with draft buttons
    for index, row in top_20_players.iterrows():
        col1, col2, col3 = st.columns(3)

        # Check if player is among the suggested players for upcoming turns
        player_name = row['Name']
        player_details = f"{player_name} - {row['Position']} - {row['ProjectedFantasyPoints']} points - {row['AverageDraftPositionPPR']} ADP - {row['ByeWeek']} bye"
        
        if player_name == next_suggested_player['Name']:
            player_display = f"**<span style='color:red;'>{player_details}</span>**"
            with col1:
                st.markdown(player_display, unsafe_allow_html=True)
        else:
            with col1:
                st.write(player_details)

        with col2:
            # Add a draft button for each player
            draft_button = st.button(f"Draft {player_name}", key=row['Name'])
            # When the "Draft" or "Draft to My Team" button is clicked:
            if draft_button:
                set_draft_status(fantasy_data, row['Name'], True)
                fantasy_data.to_csv(csv_path, index=False)

                # Get the next suggested player
                next_suggested_player = suggest_pick(fantasy_data, my_draft_position, num_users)
                if next_suggested_player is not None:
                    st.write(f"The next suggested pick is: {next_suggested_player['Name']}")
                else:
                    st.write("All players have been drafted.")


    # Check if a player has been drafted and update the data accordingly
    if st.session_state.drafted_name:
        set_draft_status(fantasy_data, st.session_state.drafted_name, True)
        fantasy_data.to_csv(csv_path, index=False)
        st.write(f"{st.session_state.drafted_name} has been drafted!")
        # Reset the drafted name in session state
        st.session_state.drafted_name = None

if __name__ == "__main__":
    main()
