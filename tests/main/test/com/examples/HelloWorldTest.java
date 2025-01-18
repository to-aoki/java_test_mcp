package com.example;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Assertions;

public class HelloWorldTest {

    @Test
    public void sayHello() {
        HelloWorld hello = new HelloWorld();
        Assertions.assertEquals(hello.hello(), "hello, world");
    }

}
