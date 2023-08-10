# This script takes the FantasyPros endpoint and converts it to a CSV file
# then allows you to determine the best available draft pick based on the rest available

import pandas as pd
import requests
import csv
from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
import streamlit as st

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
    df['my_team'] = ''
    df['my_team_round'] = ''
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

def set_draft_status(df, player_name, is_drafted=True, to_my_team=False, draft_round=None):
    """Set the draft status of a player."""
    player_index = df[df['Name'] == player_name].index[0]
    df.at[player_index, 'is_drafted'] = is_drafted
    
    if is_drafted:
        # If the player is being drafted, set their draft order
        max_order = df['draft_order'].max()
        next_order = 1 if pd.isna(max_order) else max_order + 1
        df.at[player_index, 'draft_order'] = next_order
    
    if to_my_team:
        df.at[player_index, 'my_team'] = True
        if draft_round:
            df.at[player_index, 'my_team_round'] = draft_round

# Streamlit
def main():
    st.title("Fantasy Football Draft Assistant")

    # Load data
    fantasy_data = load_fantasy_data(csv_path)

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
            lambda row: f"🏈 {row['Name']} - {row['Position']}" if row.get('my_team', False) else f"{row['Name']} - {row['Position']}",
            axis=1
        )
        
        # Display only the modified 'Display' column
        st.table(drafted_players['Display'])


    
    # Initialize session state variable for drafted player name
    if 'drafted_name' not in st.session_state:
        st.session_state.drafted_name = None

    # Display the top 20 filtered results with draft buttons
    for index, row in top_20_players.iterrows():
        col1, col2, col3 = st.columns(3)
        with col1:
            st.write(f"{row['Name']} - {row['Position']} - {row['ProjectedFantasyPoints']} points - {row['AverageDraftPositionPPR']} ADP - {row['ByeWeek']} bye")
        with col2:
            # Add a draft button for each player
            draft_button = st.button(f"Draft {row['Name']}", key=row['Name'])
            if draft_button:
                set_draft_status(fantasy_data, row['Name'], True, to_my_team=False)
                fantasy_data.to_csv(csv_path, index=False)
                st.write(f"{row['Name']} has been drafted!")
        with col3:
            # Add a "Draft to My Team" button for each player
            my_team_button = st.button(f"Draft to My Team", key=f"MyTeam_{row['Name']}")
            if my_team_button:
                # Determine the current draft round for your team
                current_round = fantasy_data[fantasy_data['my_team'] == True].shape[0] + 1

                # When the "Draft to My Team" button is clicked:
                set_draft_status(fantasy_data, row['Name'], True, to_my_team=True, draft_round=current_round)
                fantasy_data.to_csv(csv_path, index=False)
                st.write(f"{row['Name']} has been drafted to your team!")

    # Check if a player has been drafted and update the data accordingly
    if st.session_state.drafted_name:
        set_draft_status(fantasy_data, st.session_state.drafted_name, True)
        fantasy_data.to_csv(csv_path, index=False)
        st.write(f"{st.session_state.drafted_name} has been drafted!")
        # Reset the drafted name in session state
        st.session_state.drafted_name = None

if __name__ == "__main__":
    main()
