class AddOne:
    def apply(self, value):
        return value + 1


class MultiplyAndAdd:
    def apply(self, value):
        return value * 3 + 1


class SubtractOne:
    def apply(self, value):
        return value - 1


class XorValue:
    def apply(self, value):
        return value ^ 0x5A5A


operations = (AddOne(), MultiplyAndAdd(), SubtractOne(), XorValue())
value = 1
for index in range(5_000_000):
    value = operations[index & 3].apply(value) & 0xFFFFFFFF

print(value)
