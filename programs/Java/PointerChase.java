public class PointerChase {
    private static final class Node {
        private final int index;
        private Node next;

        private Node(int index) {
            this.index = index;
        }
    }

    public static void main(String[] args) {
        Thread.currentThread().setName("checkpoint-main");
        int nodeCount = 8192;
        Node[] nodes = new Node[nodeCount];
        for (int index = 0; index < nodeCount; index++) {
            nodes[index] = new Node(index);
        }
        for (int index = 0; index < nodeCount; index++) {
            nodes[index].next = nodes[(index + 257) & (nodeCount - 1)];
        }

        Node current = nodes[0];
        for (int iteration = 0; iteration < 4_000_000; iteration++) {
            current = current.next;
        }

        System.out.println(current.index);
    }
}
