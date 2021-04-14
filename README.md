# ansible-satellite
Satellite dynamic inventory for ansible

This is based on the script by Fotis Gimian shamelessly copied from [here](https://gist.github.com/fgimian/f83fca522ca11d915a41e5ca2fd1b9de)

To make this work, we need:
 * A working gpg-agent with a gpg encrypted file containing only our password (with
   no trailing whitespace, currently!)
 * A satellite ini containing the details needed to find the satellite.


Setting up gpg-agent and password file
----

### Create key.
`gpg --gen-key`

### Store password.
`gpg -r $gpgid -o password.gpg -e`

### Read password. (for testing)
`gpg --quiet --no-tty -d password.gpg`


Setting up satellite.ini
----
Create a file called satellite.ini with the following content:
```
[satellite]
base_url = https://erarhs01/
username = $gpgid
password_file = password.gpg
```

Test it works
----
`ansible-inventory -i ./inventory/ --graph`

