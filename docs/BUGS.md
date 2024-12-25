# BUGS

* if the api_transaction stuff is turned on, it is possible to simply 
  update the UI too fast and get errors thrown.
  * maybe the sqlalchemy hooks, although elegant, are a bad idea.
  * in fact, maybe sqlalchemy is a bad idea.