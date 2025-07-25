frontend code:
├── frontend/ # Angular 17 project
│ ├── src/
│ │ ├── app/
│ │ │ ├── components/
│ │ │ │ ├── chat-window/ # Displays chat messages
│ │ │ │ ├── sidebar-history/ # Chat history list
│ │ │ │ └── message-input/ # Input field + send button
│ │ │ ├── services/
│ │ │ │ └── chat.service.ts # Handles API requests
│ │ │ ├── app.component.ts
│ │ │ └── app.module.ts
│ │ └── assets/
│ ├── index.html
│ └── styles.css

On load, the chatbot greets the user with:
“How can I help you with?”

Users can enter queries via the MessageInputComponent.

The ChatService handles communication using Angular’s HttpClient to send a POST request to the Flask backend at /chat.

The Flask backend processes the query using your OLBB estimation logic and returns a response.

The ChatWindowComponent renders the conversation, including both system and user messages.

Messages are stored in localStorage for persistent session history.

The SidebarHistoryComponent displays a scrollable list of previous user messages for quick navigation.
💡 Key Features
✅ SidebarHistoryComponent
Displays prior queries and responses.

Utilizes localStorage for session persistence.

Enables easy navigation across chat history.

💬 ChatWindowComponent
Central area for displaying ongoing chat.

Shows system and user messages chronologically.

Includes a persistent header: "OLBB Estimation Search Chatbot".

✏️ MessageInputComponent
Input field with a send button.

Triggers message dispatch via ChatService.

🎨 UI & Styling
Uses CSS or TailwindCSS for a responsive, modern look.

Easily supports UI enhancements like:

Markdown rendering

Loading spinners

Message tagging or filtering. everything once created you can zip all the files make sure it is properly aligned based on angular folder structure. Make sure there should be a file for flask server. Correct all sort of error if found.

Additional Improvement Implementation steps.
1. Add a "Clear History" button to wipe localStorage.
2.  Group messages into chat sessions (not individual messages)
Goal: Once a user finishes chatting and navigates away or refreshes, save the conversation as a single session.
3 Implement search/filter for easier navigation through past queries.
4 Change the send button to upper arrow.
once click it will change into a rectangle.
also, Show a loading spinner or "Bot is typing..." message while waiting for the backend response.
5. Visually group messages by sender (User vs. Bot) using bubbles aligned left/right. Use Avatars for this.
6. Allow users to switch between light and dark themes.
7. One list item per chat session
On click → load entire chat (all messages)
On hover → show short preview or timestamp
8. AVATARS - Use flex or grid in the message component to align avatars and message bubbles.
Use rounded avatar backgrounds with initials inside
9. Typing indicator -> Show “Bot is typing…”
10. Session title auto-generation like Title = First message or prompt
11. Towards the end of the response provide a thumbs up and down icon as well as copy the response option. End Chat and after X minutes of inactivity

