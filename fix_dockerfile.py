content = open("/opt/ax-server/Dockerfile").read()
if "COPY data/" not in content:
    content = content.replace("COPY share_cards/ share_cards/", "COPY share_cards/ share_cards/\nCOPY data/ data/")
    open("/opt/ax-server/Dockerfile", "w").write(content)
    print("Added COPY data/ data/ to Dockerfile")
else:
    print("Already has COPY data/")
print(open("/opt/ax-server/Dockerfile").read())
