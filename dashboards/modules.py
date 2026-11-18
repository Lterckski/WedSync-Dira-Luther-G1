"""
What each role will be able to do, taken from the SDD feature list (Section 2.2)
and business rules (Section 3.1). Shown on each dashboard so every role sees
the tools that belong to it. Tools open phase by phase; AVAILABLE_FEATURES lists
the ones each role can use now.
"""
from accounts.models import Role

ROLE_MODULES = {
    Role.COUPLE: [
        ("Wedding workspace", "Create your wedding profile and invite your coordinator and vendors.", "F-02"),
        ("Budget and expenses", "Set a budget per category and log every expense against it.", "F-03"),
        ("Vendors and contracts", "Track each vendor's contract and its payment milestones.", "F-04"),
        ("Guests and RSVPs", "Keep the guest list with RSVPs, dietary needs and accessibility notes.", "F-05"),
        ("Seating planner", "Seat attending guests at tables without going over capacity.", "F-06"),
        ("Messages", "Talk with your coordinator and vendors in one place.", "F-07"),
        ("Day-of timeline", "Follow the run-of-show live on the day.", "F-08"),
    ],
    Role.COORDINATOR: [
        ("Weddings you manage", "Open each couple's workspace and manage who is a member.", "F-02"),
        ("Budgets", "Review category budgets and expenses with the couple.", "F-03"),
        ("Vendors and contracts", "Book vendors, track contract status and payment due dates.", "F-04"),
        ("Guests and seating", "Help with RSVPs and table assignments.", "F-05, F-06"),
        ("Messages", "Coordinate with couples and vendors per wedding.", "F-07"),
        ("Day-of timeline", "Run the schedule and update each item's status live — only coordinators can.", "F-08"),
    ],
    Role.VENDOR: [
        ("Your bookings", "See the weddings where you have an active contract.", "F-02"),
        ("Contracts and payments", "Check your contract status and payment milestones.", "F-04"),
        ("Messages", "Talk with the couple and coordinator for each booking.", "F-07"),
        ("Day-of schedule", "See your call times and live updates on the day.", "F-08"),
    ],
}

ROLE_INTROS = {
    Role.COUPLE: "Everything for your wedding will live here — budget, guests, vendors and the day itself.",
    Role.COORDINATOR: "Your weddings, vendors and run-of-show schedules will live here.",
    Role.VENDOR: "The weddings you're booked for, your contracts and your call times will live here.",
}

# Features each role can already use (the rest are marked "Coming soon").
AVAILABLE_FEATURES = {
    Role.COUPLE: {"F-02"},
    Role.COORDINATOR: {"F-02"},
    Role.VENDOR: set(),
}
