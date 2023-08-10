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

csv_path = "/Users/coley/Downloads/fantasy_players.csv"

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

# if __name__ == "__main__":
#     # Load the fantasy data
#     fantasy_data = load_fantasy_data("csv_path")
    
#     # Setup typeahead for player names
#     player_completer = WordCompleter(list(fantasy_data['Name']), ignore_case=True)
    
#     while True:
#         # Check if any players remain undrafted
#         if fantasy_data['is_drafted'].all():
#             print("All players have been drafted!")
#             break
        
#         # Prompt the user for the desired position, exit, or a player's name that someone else has drafted
#         user_input = prompt("Enter the position you want to draft (e.g., QB, RB, WR, TE, K, DEF), 'exit' to stop, or type in a player's name that someone else has drafted: ", completer=player_completer).strip().upper()
        
#         if user_input == "EXIT":
#             print("Exiting the draft.")
#             break
        
#         # If the user input matches a player's name
#         elif user_input.title() in fantasy_data['Name'].values:
#             set_draft_status(fantasy_data, user_input.title(), True)
#             # Save the updated DataFrame back to the CSV
#             fantasy_data.to_csv("csv_path", index=False)
#             print(f"{user_input.title()} has been drafted by someone else!")
#             continue
        
#         # If the user input is a position
#         else:
#             # Get the next best available player for the specified position
#             best_available = get_next_best_available(fantasy_data, user_input)
            
#             if best_available is None:  # If no available players for the specified position
#                 print(f"No available players for position {user_input}")
#                 continue
            
#             print(f"Next best available player for position {user_input}: {best_available['Name']} (Projected Points: {best_available['ProjectedFantasyPoints']})")
            
#             # Prompt user to set the is_drafted flag for the suggested player
#             draft_decision = input(f"Do you want to draft {best_available['Name']}? (yes/no): ").strip().lower()
            
#             if draft_decision == 'yes':
#                 set_draft_status(fantasy_data, best_available['Name'], True)
#                 # Save the updated DataFrame back to the CSV
#                 fantasy_data.to_csv("csv_path", index=False)
#                 print(f"{best_available['Name']} has been drafted!")

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

    # Display drafted players in a separate table, sorted by draft order
    drafted_players = fantasy_data[fantasy_data['is_drafted'] == True].sort_values(by='draft_order')
    if not drafted_players.empty:
        st.subheader("Drafted Players")
        st.table(drafted_players[['Name', 'Position', 'draft_order']])
    
    # Initialize session state variable for drafted player name
    if 'drafted_name' not in st.session_state:
        st.session_state.drafted_name = None

    # Display filtered results with draft buttons
    for index, row in filtered_data.iterrows():
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"{row['Name']} - {row['Position']} - {row['ProjectedFantasyPoints']} points")
        with col2:
            # Add a draft button for each undrafted player
            draft_button = st.button(f"Draft {row['Name']}", key=row['Name'])
            if draft_button:
                st.session_state.drafted_name = row['Name']

    # Check if a player has been drafted and update the data accordingly
    if st.session_state.drafted_name:
        set_draft_status(fantasy_data, st.session_state.drafted_name, True)
        fantasy_data.to_csv(csv_path, index=False)
        st.write(f"{st.session_state.drafted_name} has been drafted!")
        # Reset the drafted name in session state
        st.session_state.drafted_name = None

if __name__ == "__main__":
    main()