CREATE TABLE Stuff(
  sid INTEGER PRIMARY KEY,
  sname TEXT NOT NULL
);

CREATE TABLE Auth(
  aid INTEGER PRIMARY KEY,
  login TEXT UNIQUE NOT NULL CHECK (login NOT LIKE '%@%'),
  email TEXT UNIQUE NOT NULL CHECK (email LIKE '%@%'),
  upass TEXT NOT NULL,
  admin BOOLEAN NOT NULL DEFAULT FALSE
);
