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

def set_draft_status(df, player_name, drafted=True, to_my_team=False):
    """
    Function to set a player's draft status in the DataFrame.
    If drafted, it will also set the draft order.
    """
    idx = df[df['Name'] == player_name].index[0]
    
    # Set the draft status
    df.at[idx, 'is_drafted'] = drafted

    # If the player is drafted, set the draft order
    if drafted:
        max_order = df['draft_order'].max()
        if pd.isna(max_order) or max_order == '':
            next_order = 1
        else:
            next_order = int(max_order) + 1
        df.at[idx, 'draft_order'] = next_order

    # If the player is drafted to "my team", set the 'my_team' flag
    if to_my_team:
        df.at[idx, 'my_team'] = True


def suggest_pick(df, my_draft_position, num_users):
    # If we have a current suggested player and he's still undrafted, suggest him again
    if 'suggested_player_name' in st.session_state and st.session_state.suggested_player_name in df['Name'].values and not df[df['Name'] == st.session_state.suggested_player_name].iloc[0]['is_drafted']:
        return df[df['Name'] == st.session_state.suggested_player_name].iloc[0]

    # Set positional constraints
    roster_constraints = {
        'QB': 1,
        'WR': 2,
        'RB': 2,
        'TE': 1,
        'FLEX': 1,
        'DST': 1,
        'K': 1
    }

    # Check current composition of your team
    my_team = df[df['my_team'] == True]
    for position in ['QB', 'WR', 'RB', 'TE', 'DST', 'K']:
        roster_constraints[position] -= len(my_team[my_team['Position'] == position])

    # If Flex hasn't been filled, check for best available between WR, RB, TE
    if roster_constraints['FLEX'] > 0:
        potential_flex = my_team[(my_team['Position'] == 'WR') | 
                                (my_team['Position'] == 'RB') | 
                                (my_team['Position'] == 'TE')]
        if len(potential_flex) < 3:  # 2 WRs + 1 RB or 2 RBs + 1 WR would fill the Flex
            roster_constraints['TE'] -= len(potential_flex)

    total_drafted_players = df[df['is_drafted'] == True].shape[0]
    current_round = (total_drafted_players // num_users) + 1

    # Determine the number of picks before your turn
    if current_round % 2 == 1:  # Odd rounds
        picks_before_your_turn = my_draft_position - (total_drafted_players % num_users)
    else:  # Even rounds
        picks_before_your_turn = num_users - (total_drafted_players % num_users) + my_draft_position

    # Get undrafted players sorted by projected points
    undrafted_players = df[df['is_drafted'] == False].sort_values(by='ProjectedFantasyPoints', ascending=False).reset_index(drop=True)

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
    top_20_players = filtered_data.sort_values(by='ProjectedFantasyPoints', ascending=False).head(20)

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
                set_draft_status(fantasy_data, row['Name'], True)
                fantasy_data.to_csv(csv_path, index=False)
                # Remove the suggested player if he's drafted
                if row['Name'] == st.session_state.suggested_player_name:
                    del st.session_state.suggested_player_name
        
        with col3:
            # Add a "Draft to My Team" button for each player
            my_team_button = st.button(f"Draft {row['Name']} to My Team", key=f"MyTeam_{row['Name']}")
            if my_team_button:
                set_draft_status(fantasy_data, row['Name'], True, to_my_team=True)
                fantasy_data.to_csv(csv_path, index=False)
                st.write(f"{row['Name']} has been drafted to your team!")
                # Remove the suggested player if he's drafted
                if row['Name'] == st.session_state.suggested_player_name:
                    del st.session_state.suggested_player_name

if __name__ == "__main__":
    main()
