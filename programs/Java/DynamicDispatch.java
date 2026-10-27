public class DynamicDispatch {
    private interface Operation {
        int apply(int value);
    }

    private static final class AddOne implements Operation {
        @Override
        public int apply(int value) {
            return value + 1;
        }
    }

    private static final class MultiplyAndAdd implements Operation {
        @Override
        public int apply(int value) {
            return value * 3 + 1;
        }
    }

    private static final class SubtractOne implements Operation {
        @Override
        public int apply(int value) {
            return value - 1;
        }
    }

    private static final class XorValue implements Operation {
        @Override
        public int apply(int value) {
            return value ^ 0x5A5A;
        }
    }

    public static void main(String[] args) {
        Thread.currentThread().setName("checkpoint-main");
        Operation[] operations = {
            new AddOne(),
            new MultiplyAndAdd(),
            new SubtractOne(),
            new XorValue()
        };

        int value = 1;
        for (int index = 0; index < 5_000_000; index++) {
            value = operations[index & 3].apply(value);
        }

        System.out.println(Integer.toUnsignedString(value));
    }
}
