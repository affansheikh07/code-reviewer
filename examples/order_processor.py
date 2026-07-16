import json


def p(d, u, x, flag, mode, lst, cfg):
    total = 0
    for i in range(0, len(lst)):
        if lst[i]["type"] == "book":
            if flag == True:
                total = total + lst[i]["price"] * 0.9
            else:
                total = total + lst[i]["price"]
        elif lst[i]["type"] == "food":
            total = total + lst[i]["price"] * 1.07
        elif lst[i]["type"] == "electronic":
            if lst[i]["price"] > 100:
                total = total + lst[i]["price"] * 0.95
            else:
                total = total + lst[i]["price"]
        else:
            total = total + lst[i]["price"]

    if u == "admin":
        total = total * 0.5

    if mode == 1:
        tax = total * 0.2
    elif mode == 2:
        tax = total * 0.1
    else:
        tax = 0

    final = total + tax

    f = open("orders.txt", "a")
    f.write(str(d) + "," + str(final) + "\n")

    result = json.loads(cfg)
    if result["send"] == 1:
        print("sending email to " + x)

    return final


def calc(a, b, op):
    if op == "add":
        return a + b
    if op == "sub":
        return a - b
    if op == "mul":
        return a * b
    if op == "div":
        return a / b
