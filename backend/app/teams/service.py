from ..models import Team, TeamMember, Board, BoardMember, BoardColumn

def create_team(db, actor, name, description=None):
    team = Team(name=name, description=description, created_by_id=actor.id, owner_id=actor.id)
    db.add(team)
    db.flush()
    db.add(TeamMember(team_id=team.id, user_id=actor.id, role="owner"))
    return team

def create_board(db, team, actor, name, description=None, visibility="team"):
    board = Board(name=name, description=description, team_id=team.id,
                  created_by_id=actor.id, visibility=visibility, is_public=False, revision=0)
    db.add(board)
    db.flush()
    db.add(BoardMember(board_id=board.id, user_id=actor.id, role="admin"))
    db.add_all([BoardColumn(board_id=board.id, name=name, position=index)
                for index, name in enumerate(("Todo", "In Progress", "Done"))])
    return board
