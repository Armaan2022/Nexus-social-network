# [NEXUS - Distributed Social Networking System]
Nexus is a lightweight, decentralized social networking platform. It enables users on independent servers (nodes) to interact seamlessly through posts, likes, comments, and follows — all without relying on a centralized provider like Facebook or Twitter.

Each user operates on a node, and the platform uses an inbox-based model to deliver content and interactions across the network. Public, unlisted, and friends-only posts can be created and shared, with appropriate visibility rules applied. When a user follows someone on another node, their content is aggregated into the local stream, allowing cross-node social interaction.

This system demonstrates the core mechanics of federated social media while maintaining simplicity suitable for educational and prototype purposes.

## 🚀 Features

- User registration and authentication
- Creating, editing, and deleting posts
- Public/private/friends-only post visibility
- Remote post fetching from other servers (federation)
- Friend requests and author following
- Markdown support for posts
- Image upload support
- Admin interface for moderation
- RESTful API for frontend/backend integration

## 🛠️ Tech Stack

- **Backend**: Django, Django REST Framework
- **Frontend**: Plain HTML/CSS with Bootstrap
- **Database**: SQLite (development), PostgreSQL
- **Other**: Docker, GitHub Actions (CI), Postman (API testing)

Documentation:
https://docs.google.com/document/d/1tQ_etSlGM9fDB0vRXVxIA3BrdkX9IkTgbvFUmBrdFrc/edit?usp=sharing
