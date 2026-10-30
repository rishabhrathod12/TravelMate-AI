"""Application services: the rules between the API and the workflow (ARCHITECTURE §3).

Every access check lives here, not only in route handlers, so any entry point is covered
(SECURITY §2): each method takes the caller's owner and compares it with the record's owner.
Records are held in memory until persistence exists (M9) and are lost on restart.
"""
